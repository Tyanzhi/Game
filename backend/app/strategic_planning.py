from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random


ACTIONS = (
    "observe",
    "diplomatic_outreach",
    "economic_adjustment",
    "defensive_posture",
    "public_statement",
)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _rng(seed: int, *parts: object) -> random.Random:
    raw = ":".join(str(x) for x in (seed, *parts)).encode()
    return random.Random(int(hashlib.sha256(raw).hexdigest()[:16], 16))


@dataclass(frozen=True)
class ScenarioOutcome:
    actor_id: str
    action: str
    horizon: int
    mean_utility: float
    downside: float
    upside: float
    variance: float
    samples: int


@dataclass(frozen=True)
class CounterfactualResult:
    baseline_action: str
    alternative_action: str
    utility_delta: float
    risk_delta: float
    preferred_under_model: str


@dataclass(frozen=True)
class RepeatedGameState:
    cooperation_rate: float
    retaliation_rate: float
    equilibrium_hint: str


def monte_carlo_action_value(
    actor_id: str,
    action: str,
    base_utility: float,
    risk: float,
    horizon: int,
    seed: int,
    samples: int = 64,
    crisis_intensity: float = 0.0,
    market_stress: float = 0.0,
    belief_uncertainty: float = 0.5,
) -> ScenarioOutcome:
    rng = _rng(seed, actor_id, action, horizon)
    values = []

    for _ in range(max(8, int(samples))):
        value = float(base_utility)
        current_crisis = clamp(crisis_intensity)
        current_market = clamp(market_stress)
        uncertainty = clamp(belief_uncertainty)

        for step in range(max(1, int(horizon))):
            shock = rng.gauss(0.0, 0.035 + uncertainty * 0.025)
            crisis_drift = rng.uniform(-0.035, 0.045) + current_market * 0.008
            market_drift = rng.uniform(-0.03, 0.03) + current_crisis * 0.006

            current_crisis = clamp(current_crisis + crisis_drift)
            current_market = clamp(current_market + market_drift)

            action_bonus = {
                "observe": (1.0 - uncertainty) * 0.005,
                "diplomatic_outreach": (1.0 - current_crisis) * 0.012,
                "economic_adjustment": current_market * 0.014,
                "defensive_posture": current_crisis * 0.016,
                "public_statement": 0.004,
            }.get(action, 0.0)

            risk_cost = float(risk) * (0.018 + current_crisis * 0.010)
            value += action_bonus + shock - risk_cost

        values.append(clamp(value))

    values.sort()
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    low_index = max(0, int(len(values) * 0.10) - 1)
    high_index = min(len(values) - 1, int(len(values) * 0.90))

    return ScenarioOutcome(
        actor_id=actor_id,
        action=action,
        horizon=int(horizon),
        mean_utility=mean,
        downside=values[low_index],
        upside=values[high_index],
        variance=variance,
        samples=len(values),
    )


def evaluate_counterfactual(
    baseline: dict,
    alternative: dict,
    risk_aversion: float = 0.5,
) -> CounterfactualResult:
    baseline_utility = float(baseline.get("mean_utility", baseline.get("expected_utility", 0.0)))
    alternative_utility = float(alternative.get("mean_utility", alternative.get("expected_utility", 0.0)))

    baseline_risk = float(baseline.get("risk", baseline.get("variance", 0.0)))
    alternative_risk = float(alternative.get("risk", alternative.get("variance", 0.0)))

    baseline_score = baseline_utility - baseline_risk * clamp(risk_aversion)
    alternative_score = alternative_utility - alternative_risk * clamp(risk_aversion)

    return CounterfactualResult(
        baseline_action=str(baseline.get("action", "unknown")),
        alternative_action=str(alternative.get("action", "unknown")),
        utility_delta=alternative_utility - baseline_utility,
        risk_delta=alternative_risk - baseline_risk,
        preferred_under_model=(
            str(alternative.get("action", "unknown"))
            if alternative_score > baseline_score
            else str(baseline.get("action", "unknown"))
        ),
    )


def repeated_game_state(memory: dict, belief: dict) -> RepeatedGameState:
    cooperation_count = float(memory.get("cooperation_count", 0))
    pressure_count = float(memory.get("pressure_count", 0))
    total = max(1.0, cooperation_count + pressure_count)

    cooperation_rate = cooperation_count / total
    retaliation_rate = pressure_count / total

    trust = clamp(memory.get("trust", 0.5))
    hostility = clamp(memory.get("hostility", 0.0))
    perceived_cooperation = clamp(belief.get("cooperation", 0.5))

    if trust > 0.62 and perceived_cooperation > 0.60:
        equilibrium = "conditional_cooperation"
    elif hostility > 0.58 and retaliation_rate > 0.45:
        equilibrium = "retaliatory_equilibrium"
    elif abs(cooperation_rate - retaliation_rate) < 0.15:
        equilibrium = "mixed_strategy"
    else:
        equilibrium = "uncertain_repeated_game"

    return RepeatedGameState(
        cooperation_rate=clamp(cooperation_rate),
        retaliation_rate=clamp(retaliation_rate),
        equilibrium_hint=equilibrium,
    )


def update_strategy_learning(
    metadata: dict,
    actor_id: str,
    action: str,
    realized_utility: float,
    learning_rate: float = 0.15,
) -> dict:
    store = metadata.setdefault("strategy_learning", {})
    actor_store = store.setdefault(actor_id, {})
    row = actor_store.setdefault(action, {
        "q_value": 0.5,
        "count": 0,
        "last_realized_utility": None,
    })

    lr = clamp(learning_rate, 0.01, 1.0)
    previous = clamp(row.get("q_value", 0.5))
    realized = clamp(realized_utility)
    row["q_value"] = clamp(previous + lr * (realized - previous))
    row["count"] = int(row.get("count", 0)) + 1
    row["last_realized_utility"] = realized
    return row


def learned_action_bonus(metadata: dict, actor_id: str, action: str) -> float:
    row = metadata.get("strategy_learning", {}).get(actor_id, {}).get(action)
    if not row:
        return 0.0
    return (clamp(row.get("q_value", 0.5)) - 0.5) * 0.14


def plan_actor(
    actor_id: str,
    options: list[dict],
    actor_state: dict,
    belief: dict,
    metadata: dict,
    seed: int,
    horizon: int = 8,
    samples: int = 64,
) -> dict:
    crisis = clamp(actor_state.get("crisis_intensity", 0.0))
    market_stress = clamp(actor_state.get("market_stress", 0.0))
    uncertainty = clamp(belief.get("uncertainty", 0.5))
    risk_aversion = 1.0 - clamp(actor_state.get("risk_tolerance", 0.5))

    scenarios = []
    for option in options:
        action = str(option["action"])
        base = float(option.get("expected_utility", 0.0)) + learned_action_bonus(metadata, actor_id, action)
        outcome = monte_carlo_action_value(
            actor_id,
            action,
            base,
            float(option.get("risk", 0.0)),
            horizon,
            seed,
            samples=samples,
            crisis_intensity=crisis,
            market_stress=market_stress,
            belief_uncertainty=uncertainty,
        )
        scenarios.append({
            "action": action,
            "mean_utility": outcome.mean_utility,
            "downside": outcome.downside,
            "upside": outcome.upside,
            "variance": outcome.variance,
            "risk": float(option.get("risk", 0.0)),
            "planning_score": outcome.mean_utility - risk_aversion * outcome.variance,
        })

    scenarios.sort(key=lambda item: (-item["planning_score"], item["action"]))
    baseline = scenarios[0]
    counterfactuals = [
        evaluate_counterfactual(baseline, alternative, risk_aversion).__dict__
        for alternative in scenarios[1:]
    ]

    return {
        "actor_id": actor_id,
        "horizon": horizon,
        "samples": samples,
        "selected_action": baseline["action"],
        "scenarios": scenarios,
        "counterfactuals": counterfactuals,
        "planning_confidence": clamp(
            0.45
            + (
                baseline["planning_score"] - scenarios[1]["planning_score"]
                if len(scenarios) > 1 else 0.0
            ) * 1.7
            - uncertainty * 0.15
        ),
    }


def plan_multi_horizon(
    actor_id: str,
    options: list[dict],
    actor_state: dict,
    belief: dict,
    metadata: dict,
    seed: int,
    horizons: tuple[int, ...] = (3, 8, 20),
    samples: int = 48,
) -> dict:
    """Aggregate short-, medium-, and long-horizon Monte Carlo plans."""
    if not options:
        return {
            "actor_id": actor_id,
            "selected_action": "observe",
            "horizons": [],
            "aggregate": [],
            "counterfactuals": [],
            "planning_confidence": 0.0,
        }

    horizon_plans = [
        plan_actor(
            actor_id,
            options,
            actor_state,
            belief,
            metadata,
            seed + horizon,
            horizon=horizon,
            samples=samples,
        )
        for horizon in horizons
    ]

    by_action: dict[str, dict] = {}
    horizon_weights = {3: 0.45, 8: 0.35, 20: 0.20}
    default_weight = 1.0 / max(1, len(horizons))

    for plan in horizon_plans:
        weight = horizon_weights.get(int(plan["horizon"]), default_weight)
        for scenario in plan["scenarios"]:
            row = by_action.setdefault(
                scenario["action"],
                {
                    "action": scenario["action"],
                    "weighted_score": 0.0,
                    "weighted_mean": 0.0,
                    "weighted_variance": 0.0,
                    "weight": 0.0,
                    "horizons": {},
                },
            )
            row["weighted_score"] += float(scenario["planning_score"]) * weight
            row["weighted_mean"] += float(scenario["mean_utility"]) * weight
            row["weighted_variance"] += float(scenario["variance"]) * weight
            row["weight"] += weight
            row["horizons"][str(plan["horizon"])] = dict(scenario)

    aggregate = []
    for row in by_action.values():
        weight = row.pop("weight") or 1.0
        row["planning_score"] = row.pop("weighted_score") / weight
        row["mean_utility"] = row.pop("weighted_mean") / weight
        row["variance"] = row.pop("weighted_variance") / weight
        aggregate.append(row)

    aggregate.sort(key=lambda item: (-item["planning_score"], item["action"]))
    baseline = aggregate[0]
    counterfactuals = [
        evaluate_counterfactual(
            {
                "action": baseline["action"],
                "mean_utility": baseline["mean_utility"],
                "variance": baseline["variance"],
            },
            {
                "action": alternative["action"],
                "mean_utility": alternative["mean_utility"],
                "variance": alternative["variance"],
            },
            risk_aversion=1.0 - clamp(actor_state.get("risk_tolerance", 0.5)),
        ).__dict__
        for alternative in aggregate[1:]
    ]

    score_gap = (
        baseline["planning_score"] - aggregate[1]["planning_score"]
        if len(aggregate) > 1 else 0.0
    )
    uncertainty = clamp(belief.get("uncertainty", 0.5))

    return {
        "actor_id": actor_id,
        "selected_action": baseline["action"],
        "horizons": list(horizons),
        "horizon_plans": horizon_plans,
        "aggregate": aggregate,
        "counterfactuals": counterfactuals,
        "planning_confidence": clamp(0.45 + score_gap * 1.8 - uncertainty * 0.12),
    }
