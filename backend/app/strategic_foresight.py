from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _rng(seed: int, *parts: object) -> random.Random:
    raw = ":".join(str(x) for x in (seed, *parts)).encode()
    return random.Random(int(hashlib.sha256(raw).hexdigest()[:16], 16))


@dataclass(frozen=True)
class ScenarioNode:
    node_id: str
    depth: int
    probability: float
    stability: float
    market_stress: float
    crisis_intensity: float
    label: str
    parent_id: str | None = None


def build_scenario_tree(
    actor_id: str,
    stability: float,
    market_stress: float,
    crisis_intensity: float,
    seed: int,
    depth: int = 3,
    branching: int = 3,
) -> dict:
    depth = max(1, min(5, int(depth)))
    branching = max(2, min(4, int(branching)))
    root = ScenarioNode(
        node_id=f"{actor_id}:root",
        depth=0,
        probability=1.0,
        stability=clamp(stability),
        market_stress=clamp(market_stress),
        crisis_intensity=clamp(crisis_intensity),
        label="current_state",
    )
    nodes = [root.__dict__]
    frontier = [root]

    for level in range(1, depth + 1):
        next_frontier = []
        for parent in frontier:
            rng = _rng(seed, actor_id, parent.node_id, level)
            raw_probs = [rng.uniform(0.2, 1.0) for _ in range(branching)]
            total = sum(raw_probs) or 1.0
            probs = [p / total for p in raw_probs]

            for branch in range(branching):
                market = clamp(parent.market_stress + rng.uniform(-0.10, 0.12))
                crisis = clamp(parent.crisis_intensity + rng.uniform(-0.10, 0.13) + market * 0.015)
                stability_next = clamp(
                    parent.stability
                    + rng.uniform(-0.08, 0.06)
                    - crisis * 0.025
                    - market * 0.018
                )
                label = (
                    "escalation"
                    if crisis > parent.crisis_intensity + 0.04
                    else "deescalation"
                    if crisis < parent.crisis_intensity - 0.04
                    else "continuity"
                )
                node = ScenarioNode(
                    node_id=f"{actor_id}:{level}:{parent.node_id}:{branch}",
                    depth=level,
                    probability=parent.probability * probs[branch],
                    stability=stability_next,
                    market_stress=market,
                    crisis_intensity=crisis,
                    label=label,
                    parent_id=parent.node_id,
                )
                nodes.append(node.__dict__)
                next_frontier.append(node)
        frontier = next_frontier

    leaves = [node for node in nodes if node["depth"] == depth]
    probability_sum = sum(node["probability"] for node in leaves) or 1.0
    expected_stability = sum(node["stability"] * node["probability"] for node in leaves) / probability_sum
    escalation_probability = sum(
        node["probability"] for node in leaves if node["label"] == "escalation"
    ) / probability_sum

    return {
        "actor_id": actor_id,
        "depth": depth,
        "branching": branching,
        "nodes": nodes,
        "leaf_count": len(leaves),
        "expected_stability": clamp(expected_stability),
        "escalation_probability": clamp(escalation_probability),
    }


ACTION_RESOURCE_COSTS = {
    "observe": {"economic": 0.01, "security": 0.00, "diplomatic": 0.01},
    "diplomatic_outreach": {"economic": 0.02, "security": 0.00, "diplomatic": 0.08},
    "economic_adjustment": {"economic": 0.12, "security": 0.01, "diplomatic": 0.01},
    "defensive_posture": {"economic": 0.05, "security": 0.13, "diplomatic": 0.01},
    "public_statement": {"economic": 0.01, "security": 0.00, "diplomatic": 0.04},
}


def resource_feasibility(action: str, actor_state: dict) -> dict:
    costs = ACTION_RESOURCE_COSTS.get(action, {})
    capacities = {
        "economic": clamp(actor_state.get("economic_capacity", 0.5)),
        "security": clamp(actor_state.get("security_capacity", 0.5)),
        "diplomatic": clamp(actor_state.get("diplomatic_capacity", 0.5)),
    }
    margins = {
        key: capacities[key] - float(costs.get(key, 0.0))
        for key in capacities
    }
    feasible = all(value >= 0 for value in margins.values())
    strain = clamp(sum(max(0.0, -value) for value in margins.values()))
    return {
        "action": action,
        "feasible": feasible,
        "strain": strain,
        "costs": costs,
        "margins": margins,
    }


def credible_commitment(
    actor_state: dict,
    signal_credibility: float,
    sunk_cost: float,
    domestic_pressure: float,
) -> dict:
    capacity = (
        clamp(actor_state.get("economic_capacity", 0.5))
        + clamp(actor_state.get("security_capacity", 0.5))
        + clamp(actor_state.get("diplomatic_capacity", 0.5))
    ) / 3.0
    credibility = clamp(
        0.25
        + capacity * 0.28
        + clamp(signal_credibility) * 0.32
        + clamp(sunk_cost) * 0.22
        - clamp(domestic_pressure) * 0.18
    )
    return {
        "credibility": credibility,
        "credible": credibility >= 0.58,
        "mechanism": "costly_commitment",
    }


def brinkmanship_state(
    actor_a: dict,
    actor_b: dict,
    belief_a: dict,
    belief_b: dict,
) -> dict:
    risk_a = clamp(actor_a.get("risk_tolerance", 0.5))
    risk_b = clamp(actor_b.get("risk_tolerance", 0.5))
    threat_a = clamp(belief_a.get("threat", 0.5))
    threat_b = clamp(belief_b.get("threat", 0.5))
    pressure_a = clamp(actor_a.get("domestic_pressure", 0.2))
    pressure_b = clamp(actor_b.get("domestic_pressure", 0.2))

    escalation = clamp(
        (risk_a + risk_b) * 0.22
        + (threat_a + threat_b) * 0.28
        + (pressure_a + pressure_b) * 0.12
    )
    mutual_backdown = clamp(
        (1.0 - risk_a) * (1.0 - threat_a) * 0.5
        + (1.0 - risk_b) * (1.0 - threat_b) * 0.5
    )
    equilibrium = (
        "high_brinkmanship"
        if escalation >= 0.62
        else "managed_competition"
        if escalation >= 0.38
        else "low_escalation"
    )
    return {
        "escalation_risk": escalation,
        "mutual_backdown": mutual_backdown,
        "equilibrium_hint": equilibrium,
    }


def alliance_reliability(
    member: str,
    partner: str,
    relationships: dict[str, dict],
    memory: dict,
    shared_crisis: bool,
) -> float:
    rel = relationships.get(f"{member}:{partner}", {})
    diplomatic = clamp((float(rel.get("diplomatic", 0.0)) + 1.0) / 2.0)
    economic = clamp(abs(float(rel.get("economic", 0.0))))
    military = clamp(abs(float(rel.get("military", 0.0))))
    trust = clamp(memory.get("trust", 0.5))
    hostility = clamp(memory.get("hostility", 0.0))
    return clamp(
        diplomatic * 0.25
        + economic * 0.18
        + military * 0.18
        + trust * 0.24
        + (0.12 if shared_crisis else 0.0)
        - hostility * 0.17
    )


def assess_multilateral_reliability(
    coalition: dict,
    relationships: dict[str, dict],
    strategic_memory: dict,
    crisis_graph: dict,
) -> dict:
    members = list(coalition.get("members", []))
    if len(members) < 2:
        return {**coalition, "reliability": 0.0, "weakest_link": None}

    active_crises = [
        node for node in crisis_graph.get("nodes", {}).values()
        if node.get("phase") != "resolved"
    ]
    pair_scores = []
    weakest = None

    for i, member in enumerate(members):
        for partner in members[i + 1:]:
            shared_crisis = any(
                member in set(node.get("participants", []))
                and partner in set(node.get("participants", []))
                for node in active_crises
            )
            memory = strategic_memory.get(f"{member}:{partner}", {})
            score = alliance_reliability(
                member, partner, relationships, memory, shared_crisis
            )
            pair_scores.append((member, partner, score))
            if weakest is None or score < weakest[2]:
                weakest = (member, partner, score)

    reliability = sum(item[2] for item in pair_scores) / max(1, len(pair_scores))
    return {
        **coalition,
        "reliability": round(clamp(reliability), 6),
        "weakest_link": {
            "members": [weakest[0], weakest[1]],
            "score": round(weakest[2], 6),
        } if weakest else None,
    }
