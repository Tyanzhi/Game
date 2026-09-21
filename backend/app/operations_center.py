from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AlertStateModel,
    ActorModel,
    EventModel,
    EventSourceModel,
    WorldStateVersionModel,
)
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


def _operator_action(kind: str) -> str:
    return {
        "crisis": "Open crisis detail and compare escalation vs stabilization scenarios.",
        "market": "Review market drivers and inspect actors with the highest exposure.",
        "actor": "Inspect actor detail, relationships and the 1/7/30-tick scenario tree.",
        "forecast": "Review calibration, uncertainty and the evidence feeding this forecast.",
    }.get(kind, "Review the underlying evidence and causal chain.")


def _safe_http_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    return value


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
    evidence: list[dict] | None = None,
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
        "evidence": evidence or [],
        "operator_action": _operator_action(kind),
        "status": "open",
        "acknowledged_by": None,
        "acknowledged_at": None,
        "note": None,
        "first_seen_tick": None,
        "last_seen_tick": None,
        "occurrence_count": 1,
        "resolved_at": None,
    }


async def _external_evidence(
    session: AsyncSession,
    root_event_ids: set[str],
) -> dict[str, list[dict]]:
    if not root_event_ids:
        return {}

    events = (
        await session.execute(
            select(EventModel).where(EventModel.id.in_(root_event_ids))
        )
    ).scalars().all()
    sources = (
        await session.execute(
            select(EventSourceModel).where(
                EventSourceModel.event_id.in_(root_event_ids)
            )
        )
    ).scalars().all()

    urls_by_event: dict[str, list[str]] = {}
    for source in sources:
        url = _safe_http_url(source.source_url)
        if url and url not in urls_by_event.setdefault(source.event_id, []):
            urls_by_event[source.event_id].append(url)

    result: dict[str, list[dict]] = {}
    for event in events:
        metadata = event.metadata_json if isinstance(event.metadata_json, dict) else {}
        result[event.id] = [{
            "type": "external_event",
            "event_id": event.id,
            "title": event.title,
            "confidence": float(event.confidence),
            "fact_status": event.status,
            "source_count": int(event.source_count),
            "independent_source_count": int(
                metadata.get("independent_source_count", event.source_count)
            ),
            "source_quality_mean": float(
                metadata.get("source_quality_mean", 0.0)
            ),
            "confidence_model": metadata.get("confidence_model"),
            "source_urls": urls_by_event.get(event.id, [])[:8],
        }]
    return result


async def _sync_alert_lifecycle(
    session: AsyncSession,
    simulation_id: str,
    tick: int,
    alerts: list[dict],
) -> list[dict]:
    now = datetime.now(timezone.utc)
    existing = (
        await session.execute(
            select(AlertStateModel).where(
                AlertStateModel.simulation_id == simulation_id
            )
        )
    ).scalars().all()
    by_id = {row.alert_id: row for row in existing}
    active_ids = {item["id"] for item in alerts}

    for item in alerts:
        row = by_id.get(item["id"])
        if row is None:
            row = AlertStateModel(
                alert_id=item["id"],
                simulation_id=simulation_id,
                status="open",
                first_seen_tick=tick,
                last_seen_tick=tick,
                last_severity=item["severity"],
                last_title=item["title"],
                occurrence_count=1,
                updated_at=now,
            )
            session.add(row)
            by_id[row.alert_id] = row
        else:
            if row.status == "resolved":
                row.status = "open"
                row.acknowledged_by = None
                row.acknowledged_at = None
                row.note = None
                row.resolved_at = None
                row.occurrence_count = int(row.occurrence_count or 1) + 1
            row.last_seen_tick = tick
            row.last_severity = item["severity"]
            row.last_title = item["title"]
            row.updated_at = now

        item["status"] = row.status
        item["acknowledged_by"] = row.acknowledged_by
        item["acknowledged_at"] = (
            row.acknowledged_at.isoformat() if row.acknowledged_at else None
        )
        item["note"] = row.note
        item["first_seen_tick"] = int(row.first_seen_tick or tick)
        item["last_seen_tick"] = int(row.last_seen_tick or tick)
        item["occurrence_count"] = int(row.occurrence_count or 1)
        item["resolved_at"] = (
            row.resolved_at.isoformat() if row.resolved_at else None
        )

    for row in existing:
        if row.alert_id in active_ids or row.status == "resolved":
            continue
        row.status = "resolved"
        row.resolved_at = now
        row.updated_at = now

    await session.commit()

    resolved = sorted(
        (
            row for row in by_id.values()
            if row.status == "resolved"
        ),
        key=lambda row: row.resolved_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return [
        {
            "id": row.alert_id,
            "title": row.last_title or row.alert_id,
            "severity": row.last_severity or "low",
            "status": row.status,
            "first_seen_tick": int(row.first_seen_tick or 0),
            "last_seen_tick": int(row.last_seen_tick or 0),
            "occurrence_count": int(row.occurrence_count or 1),
            "acknowledged_by": row.acknowledged_by,
            "acknowledged_at": (
                row.acknowledged_at.isoformat() if row.acknowledged_at else None
            ),
            "resolved_at": (
                row.resolved_at.isoformat() if row.resolved_at else None
            ),
            "note": row.note,
        }
        for row in resolved[:20]
    ]


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

    tick = int(version.tick)
    state = version.state_json or {}
    metadata = dict(state.get("metadata") or {})
    alerts: list[dict] = []
    crisis_alert_roots: dict[str, str] = {}

    crisis_nodes = metadata.get("crisis_graph", {}).get("nodes", {})
    for crisis_id, node in crisis_nodes.items():
        if node.get("phase") == "resolved":
            continue
        intensity = _clamp(node.get("intensity", 0.0))
        escalation = _clamp(node.get("escalation", 0.0))
        contagion = _clamp(node.get("contagion", 0.0))
        uncertainty = _clamp(node.get("uncertainty", 0.0))
        phase = str(node.get("phase") or "unknown")
        phase_risk = {
            "emerging": 0.03,
            "escalating": 0.10,
            "peak": 0.16,
            "contained": -0.05,
            "decaying": -0.10,
        }.get(phase, 0.0)
        score = _clamp(
            intensity * 0.52
            + escalation * 0.22
            + contagion * 0.16
            + uncertainty * 0.10
            + phase_risk
        )
        root_event_id = str(node.get("root_event_id") or "")
        alert = _alert(
            simulation_id,
            kind="crisis",
            subject=str(crisis_id),
            title=(
                f"{str(node.get('event_type') or 'crisis').replace('_', ' ').title()} "
                "escalating"
            ),
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
                "root_event_id": root_event_id or None,
            },
        )
        alerts.append(alert)
        if root_event_id:
            crisis_alert_roots[alert["id"]] = root_event_id

    markets = metadata.get("markets", {})
    market_rules = (
        (
            "financial_stress",
            float(markets.get("financial_stress", 0.0)),
            0.18,
            "Financial stress elevated",
        ),
        (
            "energy_price",
            abs(float(markets.get("energy_price", 0.0))),
            0.16,
            "Energy price shock",
        ),
        (
            "global_trade",
            abs(min(0.0, float(markets.get("global_trade", 0.0)))),
            0.12,
            "Global trade contraction",
        ),
        (
            "commodity_supply",
            abs(min(0.0, float(markets.get("commodity_supply", 0.0)))),
            0.12,
            "Commodity supply disruption",
        ),
    )
    for field, magnitude, threshold, title in market_rules:
        if magnitude < threshold:
            continue
        score = _clamp(
            (magnitude - threshold) / max(0.01, 0.60 - threshold) * 0.65 + 0.35
        )
        alerts.append(_alert(
            simulation_id,
            kind="market",
            subject=field,
            title=title,
            message=(
                f"{field.replace('_', ' ')} moved to "
                f"{float(markets.get(field, 0.0)):+.3f}."
            ),
            score=score,
            metrics={
                "value": float(markets.get(field, 0.0)),
                "threshold": threshold,
            },
            evidence=[{
                "type": "model_state",
                "source": "global_markets",
                "tick": tick,
            }],
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
                evidence=[{
                    "type": "model_state",
                    "source": "actor_state",
                    "actor_id": actor.id,
                    "field": field,
                    "tick": tick,
                }],
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
                evidence=[{
                    "type": "model_forecast",
                    "source": predictions.get(
                        "model_version",
                        "prediction-center",
                    ),
                    "actor_id": row["actor_id"],
                    "horizon": 7,
                    "tick": tick,
                }],
            ))

    evidence_by_event = await _external_evidence(
        session,
        set(crisis_alert_roots.values()),
    )
    for item in alerts:
        root_event_id = crisis_alert_roots.get(item["id"])
        if root_event_id:
            item["evidence"] = evidence_by_event.get(root_event_id, [{
                "type": "external_event",
                "event_id": root_event_id,
                "source_urls": [],
            }])

    recent_resolved = await _sync_alert_lifecycle(
        session,
        simulation_id,
        tick,
        alerts,
    )

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

    open_alerts = [
        item for item in alerts
        if item["status"] not in {"acknowledged", "resolved"}
    ]
    if any(item["severity"] == "critical" for item in open_alerts):
        posture = "critical"
    elif any(item["severity"] == "high" for item in open_alerts):
        posture = "heightened"
    elif any(item["severity"] == "medium" for item in open_alerts):
        posture = "watch"
    else:
        posture = "normal"

    watch_actors: list[str] = []
    watch_crises: list[str] = []
    for item in open_alerts:
        for actor_id in item["actor_ids"]:
            if actor_id not in watch_actors:
                watch_actors.append(actor_id)
        if item["crisis_id"] and item["crisis_id"] not in watch_crises:
            watch_crises.append(item["crisis_id"])

    return {
        "simulation_id": simulation_id,
        "tick": tick,
        "posture": posture,
        "summary": {
            **counts,
            "open": open_count,
            "acknowledged": acknowledged_count,
            "resolved_recent": len(recent_resolved),
            "total": len(alerts),
        },
        "alerts": alerts,
        "recent_resolved": recent_resolved,
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
            "recommended_actions": [
                {
                    "alert_id": item["id"],
                    "severity": item["severity"],
                    "action": item["operator_action"],
                }
                for item in open_alerts[:5]
            ],
            "watch_actors": watch_actors[:8],
            "watch_crises": watch_crises[:8],
            "forecast_calibration": predictions.get("calibration", {}),
            "generated_from_tick": tick,
        },
    }


async def list_alert_history(
    session: AsyncSession,
    simulation_id: str,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    query = (
        select(AlertStateModel)
        .where(AlertStateModel.simulation_id == simulation_id)
        .order_by(
            AlertStateModel.updated_at.desc(),
            AlertStateModel.alert_id,
        )
        .limit(max(1, min(500, int(limit))))
    )
    if status:
        if status not in {"open", "acknowledged", "resolved"}:
            raise ValueError("Unknown alert history status")
        query = query.where(AlertStateModel.status == status)

    rows = (await session.execute(query)).scalars().all()
    return [{
        "id": row.alert_id,
        "simulation_id": row.simulation_id,
        "status": row.status,
        "title": row.last_title or row.alert_id,
        "severity": row.last_severity or "low",
        "first_seen_tick": int(row.first_seen_tick or 0),
        "last_seen_tick": int(row.last_seen_tick or 0),
        "occurrence_count": int(row.occurrence_count or 1),
        "acknowledged_by": row.acknowledged_by,
        "acknowledged_at": (
            row.acknowledged_at.isoformat() if row.acknowledged_at else None
        ),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "note": row.note,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    } for row in rows]


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
    alert = next(
        (item for item in center["alerts"] if item["id"] == alert_id),
        None,
    )
    if alert is None:
        raise ValueError(f"Unknown active alert: {alert_id}")

    row = await session.get(AlertStateModel, alert_id)
    if row is None:
        raise ValueError(f"Alert lifecycle state missing: {alert_id}")

    now = datetime.now(timezone.utc)
    row.status = status
    row.acknowledged_by = (
        acknowledged_by if status == "acknowledged" else None
    )
    row.note = note
    row.acknowledged_at = now if status == "acknowledged" else None
    row.resolved_at = None
    row.updated_at = now

    await session.commit()
    return {
        "alert_id": alert_id,
        "simulation_id": simulation_id,
        "status": row.status,
        "acknowledged_by": row.acknowledged_by,
        "acknowledged_at": (
            row.acknowledged_at.isoformat()
            if row.acknowledged_at else None
        ),
        "first_seen_tick": int(row.first_seen_tick or 0),
        "last_seen_tick": int(row.last_seen_tick or 0),
        "occurrence_count": int(row.occurrence_count or 1),
        "note": row.note,
    }
