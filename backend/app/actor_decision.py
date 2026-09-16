"""Deterministic actor decision engine under incomplete information."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import ActionModel, ActorModel, DecisionModel, EventModel, RelationshipModel

ACTIONS = ("observe", "diplomatic_outreach", "economic_adjustment", "defensive_posture", "public_statement")

@dataclass(frozen=True)
class Option:
    action: str
    expected_utility: float
    risk: float
    rationale: tuple[str, ...]

def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

def _risk(action: str, actor: ActorModel, threat: float) -> float:
    base = {"observe": .05, "diplomatic_outreach": .18, "economic_adjustment": .30, "defensive_posture": .42, "public_statement": .12}[action]
    return _clamp(base + max(0, threat - actor.escalation_threshold) * .35 - (actor.risk_tolerance - .5) * .18)

def _utility(action: str, actor: ActorModel, threat: float, pressure: float, economic_signal: float, relationship: float) -> tuple[float, tuple[str, ...]]:
    benefits = {
        "observe": .25 + actor.information_quality * .25,
        "diplomatic_outreach": actor.diplomatic_capacity * .42 + max(0, -relationship) * .30,
        "economic_adjustment": actor.economic_capacity * .38 + economic_signal * .25,
        "defensive_posture": actor.security_capacity * .40 + threat * .42,
        "public_statement": actor.diplomatic_capacity * .18 + pressure * .18,
    }
    costs = {
        "observe": threat * .34,
        "diplomatic_outreach": pressure * .12,
        "economic_adjustment": .18 + actor.domestic_pressure * .18,
        "defensive_posture": .22 + pressure * .16,
        "public_statement": .10 + threat * .08,
    }
    rationale = []
    if threat > .55: rationale.append("elevated threat perception")
    if pressure > .55: rationale.append("high domestic pressure")
    if economic_signal > .55: rationale.append("economic stress signal")
    if relationship < -.25: rationale.append("strained relationship")
    return _clamp(benefits[action] - costs[action]), tuple(rationale)

async def decide(session: AsyncSession, actor_id: str, simulation_id: str | None = None, event_limit: int = 30) -> dict:
    actor = await session.get(ActorModel, actor_id)
    if actor is None:
        raise ValueError(f"Unknown actor: {actor_id}")
    events = (await session.execute(select(EventModel).order_by(EventModel.event_timestamp.desc()).limit(event_limit))).scalars().all()
    relevant = []
    for event in events:
        metadata = event.metadata_json if isinstance(event.metadata_json, dict) else {}
        event_actors = set(metadata.get("actors", []))
        if actor_id in event_actors:
            relevant.append(event)
    relevant = relevant[:12]
    threat_types = {"conflict", "sanction", "military", "security", "crisis", "protest"}
    threat = _clamp(sum(e.confidence for e in relevant if e.event_type in threat_types) / max(1, len(relevant)) * 1.25)
    pressure = _clamp(actor.domestic_pressure + (0.10 if any(e.event_type == "protest" for e in relevant) else 0))
    economic_signal = _clamp(sum(e.confidence for e in relevant if e.event_type in {"economic_indicator", "sanction", "trade", "energy"}) / max(1, len(relevant)) * 1.1)
    rels = (await session.execute(select(RelationshipModel).where(RelationshipModel.source_actor_id == actor_id))).scalars().all()
    relationship = sum(r.diplomatic for r in rels) / max(1, len(rels))
    options = []
    for action in ACTIONS:
        utility, rationale = _utility(action, actor, threat, pressure, economic_signal, relationship)
        risk = _risk(action, actor, threat)
        adjusted = _clamp(utility - risk * (1.0 - actor.risk_tolerance))
        options.append(Option(action, adjusted, risk, rationale))
    options.sort(key=lambda item: (-item.expected_utility, item.action))
    selected = options[0]
    confidence = _clamp(0.45 + abs(selected.expected_utility - options[1].expected_utility) * 1.8 + actor.information_quality * .2)
    fingerprint = f"{actor_id}|{simulation_id}|{selected.action}|{len(relevant)}|{round(threat,4)}|{round(economic_signal,4)}"
    decision_id = "dec-" + sha256(fingerprint.encode()).hexdigest()[:24]
    factors = list(selected.rationale) or ["no dominant external signal", "bounded-information baseline"]
    information_state = {"known_events": len(relevant), "information_quality": actor.information_quality, "threat": threat, "domestic_pressure": pressure, "economic_signal": economic_signal}
    option_json = [{"action": o.action, "expected_utility": o.expected_utility, "risk": o.risk, "rationale": list(o.rationale)} for o in options]
    decision = DecisionModel(id=decision_id, actor_id=actor_id, simulation_id=simulation_id, selected_action=selected.action, confidence=confidence, situation=f"relevant_events={len(relevant)}", reasoning_factors=factors, options=option_json, information_state=information_state)
    existing = await session.get(DecisionModel, decision_id)
    if existing is None:
        session.add(decision)
    action_id = "act-" + sha256(f"{decision_id}|{selected.action}".encode()).hexdigest()[:24]
    if await session.get(ActionModel, action_id) is None:
        session.add(ActionModel(id=action_id, decision_id=decision_id, actor_id=actor_id, action_type=selected.action, status="proposed", effects={"expected_utility": selected.expected_utility, "risk": selected.risk, "confidence": confidence}))
    await session.flush()
    return {"decision_id": decision_id, "actor_id": actor_id, "selected_action": selected.action, "confidence": confidence, "reasoning_factors": factors, "information_state": information_state, "options": option_json, "action_id": action_id, "effects": {"expected_utility": selected.expected_utility, "risk": selected.risk, "confidence": confidence}}

async def decide_all(session: AsyncSession, simulation_id: str | None = None) -> list[dict]:
    actors = (await session.execute(select(ActorModel).order_by(ActorModel.id))).scalars().all()
    return [await decide(session, actor.id, simulation_id) for actor in actors]
