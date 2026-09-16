"""Deterministic strategic interaction layer for WORLD ENGINE.

The module converts independently generated actor options into pairwise strategic
interactions using payoff adjustments, bargaining, signaling and deterrence.
It does not execute actions or mutate world state.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

@dataclass(frozen=True)
class StrategicOption:
    actor_id: str
    action: str
    base_utility: float
    risk: float

@dataclass(frozen=True)
class Interaction:
    actor_a: str
    actor_b: str
    action_a: str
    action_b: str
    payoff_a: float
    payoff_b: float
    mechanism: str

COUPLED_ACTIONS = {
    ("defensive_posture", "defensive_posture"): ("security_dilemma", -0.10, -0.10),
    ("defensive_posture", "diplomatic_outreach"): ("deterrence_and_bargaining", 0.04, -0.02),
    ("diplomatic_outreach", "defensive_posture"): ("deterrence_and_bargaining", -0.02, 0.04),
    ("diplomatic_outreach", "diplomatic_outreach"): ("mutual_bargaining", 0.08, 0.08),
    ("economic_adjustment", "economic_adjustment"): ("economic_coordination", 0.04, 0.04),
    ("public_statement", "public_statement"): ("signaling", -0.03, -0.03),
}

def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))

def _relation_adjustment(relationship: float, action_a: str, action_b: str) -> tuple[float, float, str]:
    if (action_a, action_b) in COUPLED_ACTIONS:
        mechanism, a, b = COUPLED_ACTIONS[(action_a, action_b)]
        return a, b, mechanism
    if action_a == "observe" and action_b in {"defensive_posture", "public_statement"}:
        return 0.01, -0.01, "information_asymmetry"
    if action_b == "observe" and action_a in {"defensive_posture", "public_statement"}:
        return -0.01, 0.01, "information_asymmetry"
    return relationship * 0.02, relationship * 0.02, "baseline_interaction"

def evaluate_pair(a: StrategicOption, b: StrategicOption, relationship: float) -> Interaction:
    da, db, mechanism = _relation_adjustment(relationship, a.action, b.action)
    return Interaction(a.actor_id, b.actor_id, a.action, b.action,
                       _clamp(a.base_utility + da), _clamp(b.base_utility + db), mechanism)

def build_interactions(options_by_actor: dict[str, Iterable[dict]], relationships: dict[tuple[str, str], float] | None = None) -> list[Interaction]:
    relationships = relationships or {}
    normalized: dict[str, list[StrategicOption]] = {}
    for actor_id, options in options_by_actor.items():
        normalized[actor_id] = [StrategicOption(actor_id, o["action"], float(o["expected_utility"]), float(o["risk"])) for o in options]
    interactions: list[Interaction] = []
    for actor_a, actor_b in combinations(sorted(normalized), 2):
        if not normalized[actor_a] or not normalized[actor_b]:
            continue
        a, b = normalized[actor_a][0], normalized[actor_b][0]
        relationship = relationships.get((actor_a, actor_b), relationships.get((actor_b, actor_a), 0.0))
        interactions.append(evaluate_pair(a, b, relationship))
    return interactions

def apply_interaction_effects(options_by_actor: dict[str, list[dict]], interactions: list[Interaction]) -> dict[str, list[dict]]:
    """Return adjusted copies; input options are never mutated."""
    result = {actor: [dict(option) for option in options] for actor, options in options_by_actor.items()}
    for interaction in interactions:
        for actor_id, action, payoff in ((interaction.actor_a, interaction.action_a, interaction.payoff_a), (interaction.actor_b, interaction.action_b, interaction.payoff_b)):
            for option in result.get(actor_id, []):
                if option["action"] == action:
                    option["strategic_payoff"] = payoff
                    option["expected_utility"] = payoff
    return result
