from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .crisis_graph import CrisisGraph
from .models import DecisionModel, ForecastModel, WorldStateVersionModel


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


async def build_live_outlook(session: AsyncSession, simulation_id: str | None) -> dict:
    if not simulation_id:
        return {
            "simulation_id": None,
            "status": "no_live_simulation",
            "future_events": [],
            "next_actor_steps": [],
            "forecasts": [],
        }

    version = (
        await session.execute(
            select(WorldStateVersionModel)
            .where(WorldStateVersionModel.simulation_id == simulation_id)
            .order_by(WorldStateVersionModel.tick.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if version is None:
        return {
            "simulation_id": simulation_id,
            "status": "state_unavailable",
            "future_events": [],
            "next_actor_steps": [],
            "forecasts": [],
        }

    metadata = dict((version.state_json or {}).get("metadata", {}))
    graph = metadata.get("crisis_graph", {})

    future_events = []
    for crisis_id, node in graph.get("nodes", {}).items():
        if node.get("phase") == "resolved":
            continue
        event_type = str(node.get("event_type") or "")
        intensity = _clamp(node.get("intensity", 0.0))
        escalation = _clamp(node.get("escalation", 0.0))
        contagion = _clamp(node.get("contagion", 0.0))
        uncertainty = _clamp(node.get("uncertainty", 0.0))
        branches = CrisisGraph.BRANCHES.get(event_type, ())

        for branch_type in branches:
            probability = _clamp(
                0.08
                + intensity * 0.42
                + escalation * 0.20
                + contagion * 0.12
                - uncertainty * 0.10
            )
            future_events.append({
                "parent_crisis_id": crisis_id,
                "event_type": branch_type,
                "participants": list(node.get("participants", [])),
                "probability": round(probability, 6),
                "confidence": round(_clamp(1.0 - uncertainty), 6),
                "horizon_ticks": 1 if intensity >= 0.7 else 2 if intensity >= 0.4 else 3,
                "mechanism": "crisis_branch_forecast",
            })

    future_events.sort(
        key=lambda item: (-item["probability"], item["event_type"], item["parent_crisis_id"])
    )

    decisions = (
        await session.execute(
            select(DecisionModel)
            .where(DecisionModel.simulation_id == simulation_id)
            .order_by(DecisionModel.created_at.desc())
        )
    ).scalars().all()

    next_actor_steps = []
    seen_actors = set()
    for row in decisions:
        if row.actor_id in seen_actors:
            continue
        seen_actors.add(row.actor_id)
        info = row.information_state if isinstance(row.information_state, dict) else {}
        next_actor_steps.append({
            "actor_id": row.actor_id,
            "action": row.selected_action,
            "target_actor_id": info.get("target_actor_id"),
            "confidence": float(row.confidence or 0.0),
            "strategic_posture": info.get("strategic_posture"),
            "crisis_intensity": info.get("crisis_intensity", 0.0),
            "mechanism": "decision_forecast",
        })

    forecasts = (
        await session.execute(
            select(ForecastModel)
            .where(ForecastModel.simulation_id == simulation_id)
            .order_by(ForecastModel.tick.desc(), ForecastModel.id.desc())
        )
    ).scalars().all()

    forecast_payload = []
    seen_targets = set()
    for row in forecasts:
        if row.target in seen_targets:
            continue
        seen_targets.add(row.target)
        forecast_payload.append({
            "target": row.target,
            "horizon": int(row.horizon),
            "expected": float(row.expected),
            "lower": float(row.lower),
            "upper": float(row.upper),
            "confidence": float(row.confidence),
            "drivers": row.drivers or {},
        })

    return {
        "simulation_id": simulation_id,
        "status": "ready",
        "tick": int(version.tick),
        "future_events": future_events[:30],
        "next_actor_steps": next_actor_steps,
        "forecasts": forecast_payload,
    }
