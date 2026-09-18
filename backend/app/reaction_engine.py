from __future__ import annotations

import random
from dataclasses import dataclass

from .models import ActionModel, ActorModel, RelationshipModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


RESPONSE_ACTIONS = (
    "observe",
    "diplomatic_outreach",
    "economic_adjustment",
    "defensive_posture",
    "public_statement",
)


@dataclass
class ReactionPlan:
    actor_id: str
    action_type: str
    target_actor_id: str | None
    score: float
    reason: str


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


async def _relationship(session: AsyncSession, source: str, target: str):
    return (
        await session.execute(
            select(RelationshipModel)
            .where(
                RelationshipModel.source_actor_id == source,
                RelationshipModel.target_actor_id == target,
            )
        )
    ).scalar_one_or_none()


async def plan_reactions(
    session: AsyncSession,
    actions: list[dict],
    simulation_id: str,
    seed: int,
    third_party_rate: float = 0.22,
    shock_rate: float = 0.08,
) -> tuple[list[dict], list[dict]]:
    """
    Generate one-generation reactions to already executed actions.

    The RNG is seeded from the simulation seed, so the same world state + seed
    produces the same reaction sequence. Reactions never react to other reactions
    in the same pass.
    """
    rng = random.Random(seed)
    shock_types = (
        ("economic_crisis", "economic_capacity", -1.0, "economic"),
        ("energy_disruption", "economic_capacity", -1.0, "energy"),
        ("internal_crisis", "stability", -1.0, "social"),
        ("intelligence_failure", "information_quality", -1.0, "information"),
        ("natural_disaster", "stability", -1.0, "environment"),
        ("security_incident", "security_capacity", -1.0, "security"),
    )
    actors = {
        actor.id: actor
        for actor in (
            await session.execute(select(ActorModel).order_by(ActorModel.id))
        ).scalars().all()
    }

    plans: list[ReactionPlan] = []
    source_actions = [a for a in actions if not (a.get("effects") or {}).get("reaction_to_action_id")]

    for action in source_actions:
        source = action.get("actor_id")
        effects = action.get("effects") or {}
        target = effects.get("target_actor_id")
        if not source or not target or target not in actors or source == target:
            continue

        target_actor = actors[target]
        rel = await _relationship(session, target, source)
        diplomatic = float(rel.diplomatic or 0.0) if rel else 0.0

        diplomatic_delta = float(effects.get("diplomatic_delta") or 0.0)
        pressure = max(0.0, -diplomatic_delta) + max(0.0, diplomatic_delta * -2.0)
        economic_signal = abs(float(effects.get("economic_capacity_delta") or 0.0))
        security_signal = abs(float(effects.get("security_capacity_delta") or 0.0))
        information_signal = abs(float(effects.get("information_quality_delta") or 0.0))
        threat = max(0.0, -diplomatic) + pressure + economic_signal * 2.0 + security_signal * 1.5
        response_intensity = _clamp(
            0.25
            + threat * 0.65
            + float(target_actor.domestic_pressure or 0.0) * 0.15
            - float(target_actor.strategic_patience or 0.0) * 0.12
        )

        if information_signal > 0.0 and float(target_actor.information_quality or 0.0) < 0.55:
            selected = "observe"
            reason = "intelligence_uncertainty_response"
        elif security_signal > 0.0 or threat > float(target_actor.escalation_threshold or 0.6):
            selected = "defensive_posture"
            reason = "security_threshold_response"
        elif economic_signal > 0.0 and float(target_actor.economic_capacity or 0.0) > 0.25:
            selected = "economic_adjustment"
            reason = "economic_pressure_response"
        elif response_intensity < 0.34:
            selected = "diplomatic_outreach"
            reason = "low_escalation_response"
        else:
            selected = "public_statement"
            reason = "political_signal_response"

        # Information quality can convert a strong signal into observation.
        if float(target_actor.information_quality or 0.0) < 0.35 and rng.random() < 0.65:
            selected = "observe"
            reason = "uncertainty_response"

        plans.append(
            ReactionPlan(
                actor_id=target,
                action_type=selected,
                target_actor_id=source if selected == "diplomatic_outreach" else None,
                score=response_intensity,
                reason=reason,
            )
        )

        # A third actor may intervene in the same crisis. This is deliberately
        # independent of the target's reaction and is limited to one generation.
        candidates = [
            actor_id for actor_id in actors
            if actor_id not in {source, target}
        ]
        if candidates and rng.random() < third_party_rate:
            third = candidates[rng.randrange(len(candidates))]
            third_rel = await _relationship(session, third, target)
            third_diplomatic = float(third_rel.diplomatic or 0.0) if third_rel else 0.0
            third_action = "diplomatic_outreach" if third_diplomatic < 0.65 else "public_statement"
            plans.append(
                ReactionPlan(
                    actor_id=third,
                    action_type=third_action,
                    target_actor_id=target if third_action == "diplomatic_outreach" else None,
                    score=response_intensity * 0.55,
                    reason="third_party_intervention",
                )
            )

    reaction_rows: list[dict] = []
    for index, plan in enumerate(plans):
        decision_id = f"reaction-decision-{simulation_id}-{seed}-{index}"
        action_id = f"reaction-action-{simulation_id}-{seed}-{index}"
        source_action_id = source_actions[index % len(source_actions)]["action_id"] if source_actions else ""
        effects = {
            "target_actor_id": plan.target_actor_id,
            "reaction_to_action_id": source_action_id,
            "reaction_reason": plan.reason,
            "reaction_score": round(plan.score, 6),
        }
        effects = {k: v for k, v in effects.items() if v is not None}
        session.add(
            ActionModel(
                id=action_id,
                decision_id=decision_id,
                actor_id=plan.actor_id,
                action_type=plan.action_type,
                status="proposed",
                effects=effects,
            )
        )
        reaction_rows.append(
            {
                "decision_id": decision_id,
                "action_id": action_id,
                "actor_id": plan.actor_id,
                "action": plan.action_type,
                "target_actor_id": plan.target_actor_id,
                "reaction": True,
                "reason": plan.reason,
            }
        )

    await session.flush()

    shocks: list[dict] = []
    if actors and rng.random() < shock_rate:
        actor_ids = sorted(actors)
        affected = actor_ids[rng.randrange(len(actor_ids))]
        shock_name, field, direction, domain = shock_types[rng.randrange(len(shock_types))]
        magnitude = round(rng.uniform(0.006, 0.025) * direction, 6)
        shocks.append(
            {
                "source": "system",
                "target": affected,
                "field": field,
                "delta": magnitude,
                "confidence": round(rng.uniform(0.45, 0.75), 6),
                "depth": 0,
                "mechanism": "unexpected_shock",
                "event_type": shock_name,
                "domain": domain,
                "duration": rng.randint(1, 4),
            }
        )
        # Secondary causal effect: crises increase domestic pressure.
        if shock_name in {"economic_crisis", "energy_disruption", "internal_crisis", "natural_disaster"}:
            shocks.append(
                {
                    "source": "system",
                    "target": affected,
                    "field": "domestic_pressure",
                    "delta": round(rng.uniform(0.004, 0.018), 6),
                    "confidence": round(rng.uniform(0.55, 0.85), 6),
                    "depth": 0,
                    "mechanism": "shock_secondary_effect",
                    "parent_event": shock_name,
                    "duration": rng.randint(1, 4),
                }
            )

    return reaction_rows, shocks
