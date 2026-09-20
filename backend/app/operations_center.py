from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AlertStateModel, ActorModel, WorldStateVersionModel
from .prediction_center import build_prediction_center


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _alert_id(simulation_id: str, kind: str, subject: str) -> str:
    raw = f"{simulation_id}:{kind}:{subject}"
    return "alert-" + sha256(raw.encode()).hexdigest()[:28]


def _severity(score: float) -> str:
    score = _clamp(score)
    if score >= 0.82:
        return "critical"
    if score >= 0.62:
        return "high"
    if score >= 0.38:
        return "medium"
    return "low"


def _alert(
    simulation_id: str,
    *,
    kind: str,
    subject: str,
    title: str,
    message: str,
    score: float,
    actor_ids: list[str] | None = None,
    crisis_id: str | None = None,
    metrics: dict | None = None,
) -> dict:
    return {
        "id": _alert_id(simulation_id, kind, subject),
        "kind": kind,
        "subject": subject,
        "title": title,
        "message": message,
        "score": round(_clamp(score), 6),
        "severity": _severity(score),
        "actor_ids": actor_ids or [],
        "crisis_id": crisis_id,
        "metrics": metrics or {},
        "status": "open",
        "acknowledged_by": None,
        "acknowledged_at": None,
        "note": None,
    }


async def build_operations_center(
    session: AsyncSession,
    simulation_id: str,
) -> dict:
    version = (
        await session.execute(
            select(WorldStateVersionModel)
            .where(WorldStateVersionModel.simulation_id == simulation_id)
            .order_by(WorldStateVersionModel.tick.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if version is None:
        raise ValueError(f"No state for simulation: {simulation_id}")

    state = version.state_json or {}
    metadata = dict(state.get("metadata") or {})
    alerts: list[dict] = []

    crisis_nodes = metadata.get("crisis_graph", {}).get("nodes", {})
    for crisis_id, node in crisis_nodes.items():
        if node.get("phase") == "resolved":
            continue
        intensity = _clamp(node.get("intensity", 0.0))
        escalation = _clamp(node.get("escalation", 0.0))
        contagion = _clamp(node.get("contagion", 0.0))
        uncertainty = _clamp(node.get("uncertainty", 0.0))
        score = _clamp(
            intensity * 0.52
            + escalation * 0.22
            + contagion * 0.16
            + uncertainty * 0.10
        )
        alerts.append(_alert(
            simulation_id,
            kind="crisis",
            subject=str(crisis_id),
            title=f"{str(node.get('event_type') or 'crisis').replace('_', ' ').title()} escalating",
            message=(
                f"Phase {node.get('phase', 'unknown')}; intensity {intensity:.0%}, "
                f"escalation {escalation:.0%}, contagion {contagion:.0%}."
            ),
            score=score,
            actor_ids=list(node.get("participants", [])),
            crisis_id=str(crisis_id),
            metrics={
                "intensity": intensity,
                "escalation": escalation,
                "contagion": contagion,
                "uncertainty": uncertainty,
            },
        ))

    markets = metadata.get("markets", {})
    market_rules = (
        ("financial_stress", float(markets.get("financial_stress", 0.0)), 0.18, "Financial stress elevated"),
        ("energy_price", abs(float(markets.get("energy_price", 0.0))), 0.16, "Energy price shock"),
        ("global_trade", abs(min(0.0, float(markets.get("global_trade", 0.0)))), 0.12, "Global trade contraction"),
        ("commodity_supply", abs(min(0.0, float(markets.get("commodity_supply", 0.0)))), 0.12, "Commodity supply disruption"),
    )
    for field, magnitude, threshold, title in market_rules:
        if magnitude < threshold:
            continue
        score = _clamp((magnitude - threshold) / max(0.01, 0.60 - threshold) * 0.65 + 0.35)
        alerts.append(_alert(
            simulation_id,
            kind="market",
            subject=field,
            title=title,
            message=f"{field.replace('_', ' ')} moved to {float(markets.get(field, 0.0)):+.3f}.",
            score=score,
            metrics={"value": float(markets.get(field, 0.0)), "threshold": threshold},
        ))

    actors = (
        await session.execute(select(ActorModel).order_by(ActorModel.id))
    ).scalars().all()
    for actor in actors:
        actor_signals = [
            (
                "stability",
                1.0 - float(actor.stability),
                float(actor.stability) < 0.50,
                f"{actor.name} stability deteriorating",
                f"Stability is {float(actor.stability):.0%}.",
            ),
            (
                "domestic_pressure",
                float(actor.domestic_pressure),
                float(actor.domestic_pressure) > 0.55,
                f"{actor.name} domestic pressure elevated",
                f"Domestic pressure is {float(actor.domestic_pressure):.0%}.",
            ),
            (
                "information_quality",
                1.0 - float(actor.information_quality),
                float(actor.information_quality) < 0.45,
                f"{actor.name} information quality degraded",
                f"Information quality is {float(actor.information_quality):.0%}.",
            ),
        ]
        for field, score, triggered, title, message in actor_signals:
            if not triggered:
                continue
            alerts.append(_alert(
                simulation_id,
                kind="actor",
                subject=f"{actor.id}:{field}",
                title=title,
                message=message,
                score=score,
                actor_ids=[actor.id],
                metrics={field: float(getattr(actor, field))},
            ))

    predictions = await build_prediction_center(session, simulation_id)
    for row in predictions.get("actors", []):
        horizon = row.get("horizons", {}).get("7", {})
        uncertainty = _clamp(horizon.get("uncertainty", 0.0))
        crisis_intensity = _clamp(row.get("crisis_intensity", 0.0))
        if uncertainty >= 0.45:
            alerts.append(_alert(
                simulation_id,
                kind="forecast",
                subject=f"{row['actor_id']}:uncertainty:7",
                title=f"{row['actor_name']} forecast uncertainty high",
                message=(
                    f"7-tick uncertainty is {uncertainty:.0%}; "
                    f"active crisis exposure {crisis_intensity:.0%}."
                ),
                score=_clamp(uncertainty * 0.75 + crisis_intensity * 0.25),
                actor_ids=[row["actor_id"]],
                metrics={
                    "horizon": 7,
                    "uncertainty": uncertainty,
                    "expected_stability": horizon.get("expected"),
                },
            ))

    alert_ids = [item["id"] for item in alerts]
    states = []
    if alert_ids:
        states = (
            await session.execute(
                select(AlertStateModel).where(AlertStateModel.alert_id.in_(alert_ids))
            )
        ).scalars().all()
    state_by_id = {row.alert_id: row for row in states}

    for item in alerts:
        row = state_by_id.get(item["id"])
        if row is None:
            continue
        item["status"] = row.status
        item["acknowledged_by"] = row.acknowledged_by
        item["acknowledged_at"] = (
            row.acknowledged_at.isoformat() if row.acknowledged_at else None
        )
        item["note"] = row.note

    alerts.sort(
        key=lambda item: (
            -SEVERITY_ORDER[item["severity"]],
            -float(item["score"]),
            item["title"],
        )
    )

    counts = {name: 0 for name in ("critical", "high", "medium", "low")}
    open_count = 0
    acknowledged_count = 0
    for item in alerts:
        counts[item["severity"]] += 1
        if item["status"] == "acknowledged":
            acknowledged_count += 1
        else:
            open_count += 1

    open_alerts = [item for item in alerts if item["status"] != "acknowledged"]
    if counts["critical"]:
        posture = "critical"
    elif counts["high"]:
        posture = "heightened"
    elif counts["medium"]:
        posture = "watch"
    else:
        posture = "normal"

    watch_actors = []
    watch_crises = []
    for item in open_alerts:
        for actor_id in item["actor_ids"]:
            if actor_id not in watch_actors:
                watch_actors.append(actor_id)
        if item["crisis_id"] and item["crisis_id"] not in watch_crises:
            watch_crises.append(item["crisis_id"])

    return {
        "simulation_id": simulation_id,
        "tick": int(version.tick),
        "posture": posture,
        "summary": {
            **counts,
            "open": open_count,
            "acknowledged": acknowledged_count,
            "total": len(alerts),
        },
        "alerts": alerts,
        "brief": {
            "headline": (
                f"{open_count} open alerts; "
                f"{counts['critical']} critical and {counts['high']} high severity."
            ),
            "top_priorities": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "severity": item["severity"],
                }
                for item in open_alerts[:5]
            ],
            "watch_actors": watch_actors[:8],
            "watch_crises": watch_crises[:8],
            "forecast_calibration": predictions.get("calibration", {}),
            "generated_from_tick": int(version.tick),
        },
    }


async def set_alert_state(
    session: AsyncSession,
    simulation_id: str,
    alert_id: str,
    *,
    status: str,
    acknowledged_by: str | None = None,
    note: str | None = None,
) -> dict:
    if status not in {"open", "acknowledged"}:
        raise ValueError("Alert status must be 'open' or 'acknowledged'")

    center = await build_operations_center(session, simulation_id)
    alert = next((item for item in center["alerts"] if item["id"] == alert_id), None)
    if alert is None:
        raise ValueError(f"Unknown active alert: {alert_id}")

    row = await session.get(AlertStateModel, alert_id)
    now = datetime.now(timezone.utc)
    if row is None:
        row = AlertStateModel(
            alert_id=alert_id,
            simulation_id=simulation_id,
            status=status,
            acknowledged_by=acknowledged_by if status == "acknowledged" else None,
            note=note,
            acknowledged_at=now if status == "acknowledged" else None,
            updated_at=now,
        )
        session.add(row)
    else:
        row.status = status
        row.acknowledged_by = acknowledged_by if status == "acknowledged" else None
        row.note = note
        row.acknowledged_at = now if status == "acknowledged" else None
        row.updated_at = now

    await session.commit()
    return {
        "alert_id": alert_id,
        "simulation_id": simulation_id,
        "status": row.status,
        "acknowledged_by": row.acknowledged_by,
        "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
        "note": row.note,
    }
