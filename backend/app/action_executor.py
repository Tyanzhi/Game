"""Controlled execution boundary between actor decisions and world state."""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import ActionModel, ActorModel, RelationshipModel

ALLOWED_ACTIONS = {"observe", "diplomatic_outreach", "economic_adjustment", "defensive_posture", "public_statement"}

def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))

def _clamp_rel(value: float) -> float:
    return max(-1.0, min(1.0, value))

async def execute_action(session: AsyncSession, action_id: str) -> dict:
    action = await session.get(ActionModel, action_id)
    if action is None:
        raise ValueError(f"Unknown action: {action_id}")
    if action.status == "executed":
        return {"action_id": action.id, "status": "executed", "effects": action.effects}
    if action.action_type not in ALLOWED_ACTIONS:
        action.status = "rejected"
        action.effects = {"reason": "action_not_allowed"}
        await session.flush()
        return {"action_id": action.id, "status": action.status, "effects": action.effects}
    actor = await session.get(ActorModel, action.actor_id)
    if actor is None:
        action.status = "rejected"
        action.effects = {"reason": "actor_not_found"}
        await session.flush()
        return {"action_id": action.id, "status": action.status, "effects": action.effects}

    effects: dict[str, object] = {"action": action.action_type}
    if action.action_type == "observe":
        actor.information_quality = _clamp(actor.information_quality + 0.015)
        effects["information_quality_delta"] = 0.015
    elif action.action_type == "diplomatic_outreach":
        rels = (await session.execute(select(RelationshipModel).where(RelationshipModel.source_actor_id == actor.id))).scalars().all()
        for rel in rels:
            rel.diplomatic = _clamp_rel(rel.diplomatic + 0.025)
        actor.domestic_pressure = _clamp(actor.domestic_pressure - 0.005)
        effects.update({"diplomatic_delta": 0.025, "relationships_changed": len(rels), "domestic_pressure_delta": -0.005})
    elif action.action_type == "economic_adjustment":
        actor.economic_capacity = _clamp(actor.economic_capacity - 0.008)
        actor.stability = _clamp(actor.stability + 0.006)
        effects.update({"economic_capacity_delta": -0.008, "stability_delta": 0.006})
    elif action.action_type == "defensive_posture":
        actor.security_capacity = _clamp(actor.security_capacity + 0.015)
        actor.domestic_pressure = _clamp(actor.domestic_pressure + 0.01)
        effects.update({"security_capacity_delta": 0.015, "domestic_pressure_delta": 0.01})
    elif action.action_type == "public_statement":
        actor.diplomatic_capacity = _clamp(actor.diplomatic_capacity + 0.005)
        effects["diplomatic_capacity_delta"] = 0.005

    action.status = "executed"
    action.effects = effects
    await session.flush()
    return {"action_id": action.id, "status": action.status, "effects": effects}

async def execute_actions(session: AsyncSession, action_ids: list[str]) -> list[dict]:
    return [await execute_action(session, action_id) for action_id in action_ids]
