from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ActorModel,
    DecisionModel,
    ForecastModel,
    RelationshipModel,
    SimulationTickModel,
    WorldStateVersionModel,
)


async def strategic_overview(session: AsyncSession, simulation_id: str) -> dict:
    latest_version = (
        await session.execute(
            select(WorldStateVersionModel)
            .where(WorldStateVersionModel.simulation_id == simulation_id)
            .order_by(WorldStateVersionModel.tick.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    latest_tick = (
        await session.execute(
            select(SimulationTickModel)
            .where(SimulationTickModel.simulation_id == simulation_id)
            .order_by(SimulationTickModel.tick.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    actors = (
        await session.execute(select(ActorModel).order_by(ActorModel.id))
    ).scalars().all()
    relationships = (
        await session.execute(select(RelationshipModel))
    ).scalars().all()

    decision_rows = (
        await session.execute(
            select(DecisionModel)
            .where(DecisionModel.simulation_id == simulation_id)
            .order_by(DecisionModel.created_at.desc())
            .limit(max(20, len(actors) * 3))
        )
    ).scalars().all()

    forecast_rows = (
        await session.execute(
            select(ForecastModel)
            .where(ForecastModel.simulation_id == simulation_id)
            .order_by(ForecastModel.tick.desc(), ForecastModel.id.desc())
            .limit(max(20, len(actors) * 3))
        )
    ).scalars().all()

    state_json = dict(latest_version.state_json or {}) if latest_version else {}
    metadata = dict(state_json.get("metadata") or {})
    snapshot_actors = dict(state_json.get("actors") or {})

    actor_payload = []
    for actor in actors:
        snap = snapshot_actors.get(actor.id, {})
        actor_payload.append({
            "id": actor.id,
            "name": actor.name,
            "actor_type": actor.actor_type,
            "stability": float(snap.get("stability", actor.stability)),
            "economic_capacity": float(snap.get("economic_capacity", actor.economic_capacity)),
            "diplomatic_capacity": float(snap.get("diplomatic_capacity", actor.diplomatic_capacity)),
            "security_capacity": float(snap.get("security_capacity", actor.security_capacity)),
            "domestic_pressure": float(snap.get("domestic_pressure", actor.domestic_pressure)),
            "information_quality": float(snap.get("information_quality", actor.information_quality)),
            "energy_security": float(snap.get("energy_security", actor.energy_security)),
            "trade_resilience": float(snap.get("trade_resilience", actor.trade_resilience)),
        })

    relationship_payload = [{
        "source": row.source_actor_id,
        "target": row.target_actor_id,
        "diplomatic": float(row.diplomatic or 0.0),
        "economic": float(row.economic or 0.0),
        "military": float(row.military or 0.0),
        "trade": float(row.trade or 0.0),
        "energy": float(row.energy or 0.0),
    } for row in relationships]

    latest_decision_by_actor: dict[str, dict] = {}
    for row in decision_rows:
        if row.actor_id in latest_decision_by_actor:
            continue
        latest_decision_by_actor[row.actor_id] = {
            "actor_id": row.actor_id,
            "selected_action": row.selected_action,
            "confidence": float(row.confidence or 0.0),
            "reasoning_factors": row.reasoning_factors or [],
            "information_state": row.information_state or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    latest_forecast_by_target: dict[str, dict] = {}
    for row in forecast_rows:
        if row.target in latest_forecast_by_target:
            continue
        latest_forecast_by_target[row.target] = {
            "target": row.target,
            "tick": row.tick,
            "horizon": row.horizon,
            "expected": float(row.expected),
            "lower": float(row.lower),
            "upper": float(row.upper),
            "confidence": float(row.confidence),
            "drivers": row.drivers or {},
        }

    crisis_graph = metadata.get("crisis_graph", {})
    active_crises = []
    for crisis_id, node in crisis_graph.get("nodes", {}).items():
        if node.get("phase") == "resolved":
            continue
        active_crises.append({
            "id": crisis_id,
            "event_type": node.get("event_type"),
            "phase": node.get("phase"),
            "intensity": float(node.get("intensity", 0.0)),
            "participants": node.get("participants", []),
            "duration": int(node.get("duration", 0)),
            "escalation": float(node.get("escalation", 0.0)),
            "contagion": float(node.get("contagion", 0.0)),
            "uncertainty": float(node.get("uncertainty", 0.0)),
        })
    active_crises.sort(key=lambda item: (-item["intensity"], item["id"]))

    phase_log = dict(latest_tick.phase_log or {}) if latest_tick else {}
    interaction = dict(phase_log.get("interaction") or {})
    forecast_phase = dict(phase_log.get("forecast") or {})

    return {
        "simulation_id": simulation_id,
        "tick": latest_version.tick if latest_version else (latest_tick.tick if latest_tick else 0),
        "state_hash": latest_version.state_hash if latest_version else None,
        "actors": actor_payload,
        "relationships": relationship_payload,
        "markets": metadata.get("markets", {}),
        "active_crises": active_crises,
        "coalitions": metadata.get("multilateral_coalitions", interaction.get("multilateral_coalitions", [])),
        "brinkmanship": metadata.get("brinkmanship", interaction.get("brinkmanship", [])),
        "bargaining": metadata.get("bargaining", interaction.get("bargains", [])),
        "decisions": list(latest_decision_by_actor.values()),
        "forecasts": list(latest_forecast_by_target.values()),
        "forecast_calibration": metadata.get("forecast_calibration", {}),
        "strategic_memory_edges": len(metadata.get("strategic_memory", {})),
        "belief_edges": len(metadata.get("beliefs", {})),
        "pending_delayed_effects": len(metadata.get("delayed_effects", [])),
        "forecast_model": forecast_phase.get("model_version"),
    }
