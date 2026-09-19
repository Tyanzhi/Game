from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def stable_random(seed: int, *parts: object) -> random.Random:
    raw = ":".join(str(part) for part in (seed, *parts)).encode()
    value = int(hashlib.sha256(raw).hexdigest()[:16], 16)
    return random.Random(value)


def belief_key(observer: str, counterpart: str) -> str:
    return f"{observer}:{counterpart}"


def get_belief(metadata: dict, observer: str, counterpart: str) -> dict:
    beliefs = metadata.setdefault("beliefs", {})
    key = belief_key(observer, counterpart)
    if key not in beliefs:
        beliefs[key] = {
            "threat": 0.5,
            "cooperation": 0.5,
            "credibility": 0.5,
            "capability": 0.5,
            "uncertainty": 0.5,
            "last_updated_tick": 0,
        }
    return beliefs[key]


def bayesian_update(prior: float, evidence: float, reliability: float) -> float:
    prior = clamp(prior)
    evidence = clamp(evidence)
    reliability = clamp(reliability)
    prior_strength = 4.0
    evidence_strength = 4.0 * reliability
    alpha = max(0.001, prior * prior_strength) + evidence * evidence_strength
    beta = max(0.001, (1.0 - prior) * prior_strength) + (1.0 - evidence) * evidence_strength
    return clamp(alpha / (alpha + beta))


def update_belief_from_action(
    metadata: dict,
    observer: str,
    counterpart: str,
    action_type: str,
    information_quality: float,
    credibility: float,
    tick: int,
) -> dict:
    belief = get_belief(metadata, observer, counterpart)
    reliability = clamp(float(information_quality) * 0.65 + float(credibility) * 0.35)

    threat_evidence = {
        "observe": 0.45,
        "diplomatic_outreach": 0.20,
        "economic_adjustment": 0.58,
        "defensive_posture": 0.78,
        "public_statement": 0.52,
    }.get(action_type, 0.5)
    cooperation_evidence = {
        "observe": 0.45,
        "diplomatic_outreach": 0.82,
        "economic_adjustment": 0.42,
        "defensive_posture": 0.22,
        "public_statement": 0.52,
    }.get(action_type, 0.5)

    belief["threat"] = bayesian_update(belief.get("threat", 0.5), threat_evidence, reliability)
    belief["cooperation"] = bayesian_update(
        belief.get("cooperation", 0.5), cooperation_evidence, reliability
    )
    belief["credibility"] = bayesian_update(
        belief.get("credibility", 0.5), credibility, information_quality
    )
    belief["uncertainty"] = clamp(
        belief.get("uncertainty", 0.5) * (1.0 - 0.18 * reliability)
    )
    belief["last_updated_tick"] = int(tick)
    return belief


def signal_profile(
    actor_id: str,
    action_type: str,
    risk_tolerance: float,
    information_quality: float,
    seed: int,
    tick: int,
) -> dict:
    rng = stable_random(seed, actor_id, action_type, tick)
    base_cost = {
        "observe": 0.05,
        "diplomatic_outreach": 0.18,
        "economic_adjustment": 0.32,
        "defensive_posture": 0.46,
        "public_statement": 0.12,
    }.get(action_type, 0.15)

    costly_signal = clamp(base_cost + (1.0 - risk_tolerance) * 0.08)
    deception_incentive = clamp(
        risk_tolerance * 0.28
        + (1.0 - information_quality) * 0.22
        + (0.08 if action_type == "public_statement" else 0.0)
    )
    deceptive = rng.random() < deception_incentive * 0.30
    credibility = clamp(
        0.45
        + costly_signal * 0.42
        + information_quality * 0.18
        - (0.32 if deceptive else 0.0)
    )
    return {
        "costly_signal": costly_signal,
        "deception_incentive": deception_incentive,
        "deceptive": deceptive,
        "credibility": credibility,
    }


DELAYED_EFFECT_PROFILES = {
    "economic_adjustment": [
        ("economic_capacity", 0.010, 2),
        ("stability", 0.006, 3),
    ],
    "diplomatic_outreach": [
        ("diplomatic_capacity", 0.004, 2),
    ],
    "defensive_posture": [
        ("security_capacity", 0.008, 2),
        ("domestic_pressure", 0.004, 2),
    ],
    "public_statement": [
        ("diplomatic_capacity", 0.002, 1),
    ],
}


def schedule_delayed_effects(
    metadata: dict,
    actor_id: str,
    action_type: str,
    current_tick: int,
    source_action_id: str,
) -> list[dict]:
    queue = metadata.setdefault("delayed_effects", [])
    created: list[dict] = []
    for field, delta, delay in DELAYED_EFFECT_PROFILES.get(action_type, []):
        effect = {
            "source": actor_id,
            "target": actor_id,
            "field": field,
            "delta": delta,
            "due_tick": int(current_tick) + int(delay),
            "source_action_id": source_action_id,
            "mechanism": "delayed_action_effect",
        }
        queue.append(effect)
        created.append(effect)
    return created


def pop_due_effects(metadata: dict, tick: int) -> list[dict]:
    queue = metadata.setdefault("delayed_effects", [])
    due = [item for item in queue if int(item.get("due_tick", 0)) <= int(tick)]
    metadata["delayed_effects"] = [
        item for item in queue if int(item.get("due_tick", 0)) > int(tick)
    ]
    return due


def build_coalitions(
    actors: dict[str, dict],
    relationships: dict[str, dict],
    crisis_graph: dict,
) -> list[dict]:
    actor_ids = sorted(actors)
    active_nodes = [
        node for node in crisis_graph.get("nodes", {}).values()
        if node.get("phase") != "resolved"
    ]
    coalitions: list[dict] = []

    for index, actor_a in enumerate(actor_ids):
        for actor_b in actor_ids[index + 1:]:
            rel_ab = relationships.get(f"{actor_a}:{actor_b}", {})
            rel_ba = relationships.get(f"{actor_b}:{actor_a}", {})
            diplomatic = (
                float(rel_ab.get("diplomatic", 0.0))
                + float(rel_ba.get("diplomatic", 0.0))
            ) / 2.0
            economic = (
                abs(float(rel_ab.get("economic", 0.0)))
                + abs(float(rel_ba.get("economic", 0.0)))
            ) / 2.0

            shared_crisis = any(
                actor_a in set(node.get("participants", []))
                and actor_b in set(node.get("participants", []))
                for node in active_nodes
            )
            score = diplomatic * 0.45 + economic * 0.30 + (0.28 if shared_crisis else 0.0)
            if score >= 0.30:
                coalitions.append({
                    "members": [actor_a, actor_b],
                    "score": round(clamp(score), 6),
                    "basis": "shared_crisis" if shared_crisis else "interdependence",
                })

    return coalitions


@dataclass(frozen=True)
class BargainingResult:
    actor_a: str
    actor_b: str
    settlement: float
    surplus: float
    accepted: bool
    mechanism: str


def nash_bargain(
    actor_a: str,
    actor_b: str,
    utility_a: float,
    utility_b: float,
    disagreement_a: float,
    disagreement_b: float,
) -> BargainingResult:
    gain_a = max(0.0, float(utility_a) - float(disagreement_a))
    gain_b = max(0.0, float(utility_b) - float(disagreement_b))
    surplus = gain_a * gain_b

    if surplus <= 0:
        return BargainingResult(
            actor_a, actor_b, 0.0, 0.0, False, "no_mutual_surplus"
        )

    weight_a = gain_a / max(1e-9, gain_a + gain_b)
    settlement = clamp(weight_a)
    return BargainingResult(
        actor_a,
        actor_b,
        settlement,
        surplus,
        True,
        "nash_bargaining",
    )


def update_forecast_calibration(
    metadata: dict,
    target: str,
    forecast_probability: float,
    observed_high: bool,
) -> dict:
    store = metadata.setdefault("forecast_calibration", {})
    row = store.setdefault(target, {
        "count": 0,
        "brier_sum": 0.0,
        "mean_brier": None,
    })
    probability = clamp(forecast_probability)
    outcome = 1.0 if observed_high else 0.0
    score = (probability - outcome) ** 2
    row["count"] += 1
    row["brier_sum"] += score
    row["mean_brier"] = row["brier_sum"] / row["count"]
    return row


def build_multilateral_coalitions(
    actors: dict[str, dict],
    relationships: dict[str, dict],
    crisis_graph: dict,
) -> list[dict]:
    """Merge compatible bilateral coalition edges into groups of 3+ actors."""
    bilateral = build_coalitions(actors, relationships, crisis_graph)
    graph: dict[str, set[str]] = {actor_id: set() for actor_id in actors}
    edge_scores: dict[tuple[str, str], float] = {}

    for coalition in bilateral:
        a, b = coalition["members"]
        graph[a].add(b)
        graph[b].add(a)
        edge_scores[tuple(sorted((a, b)))] = float(coalition["score"])

    visited: set[str] = set()
    groups: list[dict] = []
    for actor_id in sorted(graph):
        if actor_id in visited or not graph[actor_id]:
            continue
        stack = [actor_id]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(graph[current] - component)

        visited |= component
        if len(component) < 3:
            continue

        members = sorted(component)
        scores = []
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                score = edge_scores.get(tuple(sorted((a, b))))
                if score is not None:
                    scores.append(score)

        possible_edges = len(members) * (len(members) - 1) / 2
        density = len(scores) / possible_edges if possible_edges else 0.0
        cohesion = (sum(scores) / len(scores) if scores else 0.0) * density

        shared_crises = []
        for crisis_id, node in crisis_graph.get("nodes", {}).items():
            participants = set(node.get("participants", []))
            overlap = participants & set(members)
            if len(overlap) >= 2 and node.get("phase") != "resolved":
                shared_crises.append(crisis_id)

        groups.append({
            "members": members,
            "size": len(members),
            "cohesion": round(clamp(cohesion), 6),
            "density": round(clamp(density), 6),
            "shared_crises": sorted(shared_crises),
            "basis": "multilateral_network",
        })

    groups.sort(key=lambda item: (-item["cohesion"], item["members"]))
    return groups
