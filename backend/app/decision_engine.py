from __future__ import annotations

from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .actor_decision import ACTIONS, _risk, _utility
from .game_theory import apply_interaction_effects, build_interactions
from .ir_theory import assess_ir_lenses, theory_adjustment
from .models import ActionModel, ActorModel, DecisionModel, RelationshipModel
from .strategic_memory import get_memory
from .strategic_dynamics import get_belief


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _crisis_intensity(metadata: dict, actor_id: str) -> float:
    nodes = metadata.get("crisis_graph", {}).get("nodes", {})
    relevant = [
        float(node.get("intensity", 0.0))
        for node in nodes.values()
        if actor_id in set(node.get("participants", []))
        and node.get("phase") != "resolved"
    ]
    return max(relevant, default=0.0)


def _pick_target(actor_id: str, actors: list[ActorModel], relationships: list[RelationshipModel]) -> tuple[str | None, RelationshipModel | None]:
    outgoing = [rel for rel in relationships if rel.source_actor_id == actor_id]
    if outgoing:
        outgoing.sort(key=lambda rel: (float(rel.diplomatic), rel.target_actor_id))
        return outgoing[0].target_actor_id, outgoing[0]

    alternatives = sorted(actor.id for actor in actors if actor.id != actor_id)
    return (alternatives[0], None) if alternatives else (None, None)


def _strategic_posture(
    action: str,
    theory: dict,
    own_crisis: float,
    target_crisis: float,
    risk_tolerance: float,
) -> str:
    if action == "observe":
        return "information_gathering"
    if own_crisis >= 0.55 and action in {"defensive_posture", "economic_adjustment"}:
        return "containment"
    if action == "diplomatic_outreach" and (
        theory.get("liberalism", 0.0) + theory.get("constructivism", 0.0)
    ) / 2 >= 0.48:
        return "cooperative_mediation"
    if (
        target_crisis >= 0.55
        and own_crisis < 0.40
        and risk_tolerance >= 0.55
        and action in {"public_statement", "economic_adjustment", "defensive_posture"}
    ):
        return "opportunistic_leverage"
    if action == "economic_adjustment":
        return "resilience"
    if action == "defensive_posture":
        return "deterrence"
    return "signaling"


async def decide_all(
    session: AsyncSession,
    simulation_id: str,
    world_metadata: dict | None = None,
    tick: int = 0,
) -> list[dict]:
    """
    Adaptive strategic decision layer.

    Decisions combine:
    - bounded utility/risk;
    - repeated-game memory;
    - pairwise strategic interaction;
    - IR theory lenses used as explainable scoring factors;
    - crisis and market context.

    Theory lenses are model features, not claims that any one theory is true.
    """
    metadata = world_metadata if world_metadata is not None else {}
    actors = (await session.execute(select(ActorModel).order_by(ActorModel.id))).scalars().all()
    relationships = (await session.execute(select(RelationshipModel))).scalars().all()

    markets = metadata.get("markets", {})
    financial_stress = _clamp(markets.get("financial_stress", 0.0))
    trade_stress = _clamp(abs(markets.get("global_trade", 0.0)))
    energy_stress = _clamp(abs(markets.get("energy_price", 0.0)))

    options_by_actor: dict[str, list[dict]] = {}
    targets: dict[str, str | None] = {}
    assessments: dict[str, dict] = {}
    beliefs_by_actor: dict[str, dict] = {}

    pair_relationships: dict[tuple[str, str], float] = {}
    for rel in relationships:
        pair_relationships[(rel.source_actor_id, rel.target_actor_id)] = float(rel.diplomatic)

    for actor in actors:
        target_actor_id, rel = _pick_target(actor.id, actors, relationships)
        targets[actor.id] = target_actor_id

        rel_dict = {
            "diplomatic": float(rel.diplomatic) if rel else 0.0,
            "economic": float(rel.economic) if rel else 0.0,
            "military": float(rel.military) if rel else 0.0,
            "trade": float(rel.trade) if rel else 0.0,
        }
        relationship = rel_dict["diplomatic"]

        memory = (
            get_memory(metadata, actor.id, target_actor_id)
            if target_actor_id
            else {"trust": 0.5, "hostility": 0.0, "norm_alignment": 0.5}
        )
        crisis = _crisis_intensity(metadata, actor.id)
        target_crisis = _crisis_intensity(metadata, target_actor_id) if target_actor_id else 0.0
        belief = (
            get_belief(metadata, actor.id, target_actor_id)
            if target_actor_id
            else {"threat": 0.5, "cooperation": 0.5, "credibility": 0.5, "uncertainty": 0.5}
        )

        beliefs_by_actor[actor.id] = dict(belief)

        threat = _clamp(
            max(0.0, -relationship) * 0.38
            + crisis * 0.30
            + float(actor.domestic_pressure) * 0.08
            + max(0.0, rel_dict["military"]) * 0.12
            + float(belief.get("threat", 0.5)) * 0.28
        )
        pressure = _clamp(float(actor.domestic_pressure) + financial_stress * 0.12)
        economic_signal = _clamp(
            financial_stress * 0.42
            + trade_stress * 0.33
            + energy_stress * 0.25
        )

        actor_state = {
            "stability": actor.stability,
            "economic_capacity": actor.economic_capacity,
            "diplomatic_capacity": actor.diplomatic_capacity,
            "security_capacity": actor.security_capacity,
            "domestic_pressure": actor.domestic_pressure,
            "risk_tolerance": actor.risk_tolerance,
            "strategic_patience": actor.strategic_patience,
            "information_quality": actor.information_quality,
            "energy_security": actor.energy_security,
            "trade_resilience": actor.trade_resilience,
        }
        theory = assess_ir_lenses(
            actor_state,
            relationship=rel_dict,
            memory=memory,
            crisis_intensity=crisis,
            markets=markets,
        )
        assessments[actor.id] = theory.as_dict()

        options: list[dict] = []
        for action in ACTIONS:
            utility, rationale = _utility(
                action,
                actor,
                threat,
                pressure,
                economic_signal,
                relationship,
            )
            risk = _risk(action, actor, threat)
            score = utility - risk * (1.0 - float(actor.risk_tolerance))
            score += theory_adjustment(action, theory)

            # Repeated-game effects: cooperative history supports cooperation,
            # hostile history raises the appeal of defensive behavior.
            if action == "diplomatic_outreach":
                score += (float(memory.get("trust", 0.5)) - 0.5) * 0.16
                score -= float(memory.get("hostility", 0.0)) * 0.08
                score += (float(belief.get("cooperation", 0.5)) - 0.5) * 0.14
                score += (float(belief.get("credibility", 0.5)) - 0.5) * 0.05
            elif action == "defensive_posture":
                score += float(memory.get("hostility", 0.0)) * 0.12
                score += theory.security_dilemma * 0.05
                score += max(0.0, float(belief.get("threat", 0.5)) - 0.5) * 0.16
            elif action == "observe":
                score += (1.0 - float(actor.information_quality)) * 0.10
                score += float(belief.get("uncertainty", 0.5)) * 0.08

            # Strategic opportunity under asymmetric crisis exposure.
            opportunity = max(0.0, target_crisis - crisis)
            if action in {"public_statement", "economic_adjustment"}:
                score += opportunity * float(actor.risk_tolerance) * 0.06
            elif action == "diplomatic_outreach":
                score += opportunity * float(actor.strategic_patience) * 0.04

            options.append({
                "action": action,
                "expected_utility": _clamp(score),
                "risk": risk,
                "rationale": list(rationale),
                "target_actor_id": target_actor_id,
                "theory": theory.as_dict(),
                "crisis_intensity": crisis,
                "target_crisis_intensity": target_crisis,
                "opportunity": max(0.0, target_crisis - crisis),
            })

        options.sort(key=lambda item: (-item["expected_utility"], item["action"]))
        options_by_actor[actor.id] = options

    interactions = build_interactions(options_by_actor, pair_relationships)
    adjusted_options = apply_interaction_effects(options_by_actor, interactions)

    interaction_mechanisms: dict[str, list[str]] = {actor.id: [] for actor in actors}
    for interaction in interactions:
        interaction_mechanisms[interaction.actor_a].append(interaction.mechanism)
        interaction_mechanisms[interaction.actor_b].append(interaction.mechanism)

    result: list[dict] = []
    for actor in actors:
        options = adjusted_options[actor.id]
        options.sort(key=lambda item: (-float(item["expected_utility"]), item["action"]))
        selected = options[0]
        runner_up = options[1] if len(options) > 1 else selected

        confidence = _clamp(
            0.40
            + abs(float(selected["expected_utility"]) - float(runner_up["expected_utility"])) * 1.7
            + float(actor.information_quality) * 0.22
        )
        target_actor_id = targets[actor.id]
        target_crisis = _crisis_intensity(metadata, target_actor_id) if target_actor_id else 0.0
        posture = _strategic_posture(
            selected["action"],
            assessments[actor.id],
            float(selected.get("crisis_intensity", 0.0)),
            target_crisis,
            float(actor.risk_tolerance),
        )

        fingerprint = f"{simulation_id}|{tick}|{actor.id}|{selected['action']}|{target_actor_id or '-'}"
        decision_id = "decision-" + sha256(fingerprint.encode()).hexdigest()[:24]
        action_id = "action-" + sha256(f"{fingerprint}|action".encode()).hexdigest()[:24]

        reasoning = list(selected.get("rationale") or [])
        reasoning.extend(sorted(set(interaction_mechanisms.get(actor.id, []))))
        reasoning.append(f"strategic_posture:{posture}")
        if not reasoning:
            reasoning = ["bounded_rationality_baseline"]

        information_state = {
            "target_actor_id": target_actor_id,
            "markets": dict(markets),
            "crisis_intensity": selected.get("crisis_intensity", 0.0),
            "theory_assessment": assessments[actor.id],
            "strategic_posture": posture,
            "belief_state": beliefs_by_actor.get(actor.id, {}),
            "strategic_memory": (
                get_memory(metadata, actor.id, target_actor_id)
                if target_actor_id
                else {}
            ),
        }

        existing_decision = await session.get(DecisionModel, decision_id)
        if existing_decision is None:
            session.add(DecisionModel(
                id=decision_id,
                actor_id=actor.id,
                simulation_id=simulation_id,
                situation=f"adaptive_tick={tick}",
                selected_action=selected["action"],
                confidence=confidence,
                reasoning_factors=reasoning,
                options=options,
                information_state=information_state,
            ))

        action_effects = {
            "target_actor_id": target_actor_id,
            "expected_utility": selected["expected_utility"],
            "risk": selected["risk"],
            "decision_confidence": confidence,
            "theory_assessment": assessments[actor.id],
            "strategic_mechanisms": sorted(set(interaction_mechanisms.get(actor.id, []))),
            "strategic_posture": posture,
        }
        action_effects = {k: v for k, v in action_effects.items() if v is not None}

        if await session.get(ActionModel, action_id) is None:
            session.add(ActionModel(
                id=action_id,
                decision_id=decision_id,
                actor_id=actor.id,
                action_type=selected["action"],
                status="proposed",
                effects=action_effects,
            ))

        result.append({
            "decision_id": decision_id,
            "action_id": action_id,
            "actor_id": actor.id,
            "action": selected["action"],
            "selected_action": selected["action"],
            "target_actor_id": target_actor_id,
            "confidence": confidence,
            "expected_utility": selected["expected_utility"],
            "risk": selected["risk"],
            "theory_assessment": assessments[actor.id],
            "strategic_mechanisms": sorted(set(interaction_mechanisms.get(actor.id, []))),
            "strategic_posture": posture,
        })

    await session.flush()
    return result
