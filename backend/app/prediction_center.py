from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .forecasting_engine import forecast
from .models import ActorModel, EffectModel, WorldStateVersionModel


HORIZONS = (1, 7, 30)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _calibration_quality(mean_brier: float | None) -> str:
    if mean_brier is None:
        return "unscored"
    if mean_brier <= 0.08:
        return "strong"
    if mean_brier <= 0.16:
        return "good"
    if mean_brier <= 0.25:
        return "mixed"
    return "weak"


def _actor_crisis_intensity(metadata: dict, actor_id: str) -> float:
    return max(
        (
            float(node.get("intensity", 0.0))
            for node in metadata.get("crisis_graph", {}).get("nodes", {}).values()
            if node.get("phase") != "resolved"
            and actor_id in set(node.get("participants", []))
        ),
        default=0.0,
    )


def _market_stress(metadata: dict) -> float:
    markets = metadata.get("markets", {})
    return clamp(
        abs(float(markets.get("financial_stress", 0.0)))
        + abs(float(markets.get("energy_price", 0.0))) * 0.45
        + abs(float(markets.get("trade_disruption", 0.0))) * 0.35
    )


def _drivers(actor: ActorModel, metadata: dict) -> dict[str, float]:
    crisis = _actor_crisis_intensity(metadata, actor.id)
    market = _market_stress(metadata)
    return {
        "crisis_pressure": -crisis * 0.34,
        "market_stress": -market * 0.24,
        "domestic_pressure": -float(actor.domestic_pressure) * 0.16,
        "economic_capacity": (float(actor.economic_capacity) - 0.5) * 0.15,
        "security_capacity": (float(actor.security_capacity) - 0.5) * 0.10,
        "energy_security": (float(actor.energy_security) - 0.5) * 0.08,
        "trade_resilience": (float(actor.trade_resilience) - 0.5) * 0.08,
    }


def _scenario_drivers(base: dict[str, float], scenario: str) -> dict[str, float]:
    values = dict(base)
    if scenario == "stabilization":
        values["crisis_pressure"] *= 0.45
        values["market_stress"] *= 0.65
        values["economic_capacity"] += 0.035
    elif scenario == "escalation":
        values["crisis_pressure"] *= 1.55
        values["market_stress"] *= 1.30
        values["domestic_pressure"] *= 1.25
    elif scenario == "economic_shock":
        values["market_stress"] -= 0.18
        values["economic_capacity"] -= 0.12
        values["trade_resilience"] -= 0.08
    return values


def _expected_from_forecast(result: dict) -> float:
    probs = result["probabilities"]
    return clamp(
        float(probs.get("low", 0.0)) * 0.20
        + float(probs.get("medium", 0.0)) * 0.50
        + float(probs.get("high", 0.0)) * 0.80
    )


async def build_prediction_center(
    session: AsyncSession,
    simulation_id: str,
) -> dict:
    version_rows = (
        await session.execute(
            select(WorldStateVersionModel)
            .where(WorldStateVersionModel.simulation_id == simulation_id)
            .order_by(WorldStateVersionModel.tick.desc())
            .limit(2)
        )
    ).scalars().all()
    if not version_rows:
        raise ValueError(f"No state for simulation: {simulation_id}")

    current_version = version_rows[0]
    previous_version = version_rows[1] if len(version_rows) > 1 else None
    current_state = current_version.state_json or {}
    metadata = dict(current_state.get("metadata") or {})
    previous_state = previous_version.state_json or {} if previous_version else {}
    previous_metadata = dict(previous_state.get("metadata") or {})

    actors = (
        await session.execute(select(ActorModel).order_by(ActorModel.id))
    ).scalars().all()

    actor_forecasts = []
    scenario_matrix = []
    for actor in actors:
        state = {
            "stability": float(actor.stability),
            "economic_capacity": float(actor.economic_capacity),
            "security_capacity": float(actor.security_capacity),
        }
        base_drivers = _drivers(actor, metadata)
        horizons = {}
        for horizon in HORIZONS:
            result = forecast(
                f"{actor.id}:stability",
                state,
                base_drivers,
                horizon=horizon,
                seed=int(current_version.tick) * 101 + horizon,
                base_rate=float(actor.stability),
            )
            horizons[str(horizon)] = {
                "expected": _expected_from_forecast(result),
                "probabilities": result["probabilities"],
                "uncertainty": float(result["uncertainty"]),
                "ensemble": result["ensemble"],
                "drivers": result["drivers"],
            }

        calibration = metadata.get("forecast_calibration", {}).get(
            f"{actor.id}:stability", {}
        )
        mean_brier = calibration.get("mean_brier")
        actor_forecasts.append({
            "actor_id": actor.id,
            "actor_name": actor.name,
            "current_stability": float(actor.stability),
            "crisis_intensity": _actor_crisis_intensity(metadata, actor.id),
            "horizons": horizons,
            "calibration": {
                "count": int(calibration.get("count", 0)),
                "mean_brier": (
                    float(mean_brier) if mean_brier is not None else None
                ),
                "quality": _calibration_quality(
                    float(mean_brier) if mean_brier is not None else None
                ),
            },
        })

        scenarios = {}
        for scenario in ("baseline", "stabilization", "escalation", "economic_shock"):
            scenario_horizons = {}
            drivers = _scenario_drivers(base_drivers, scenario)
            for horizon in HORIZONS:
                result = forecast(
                    f"{actor.id}:stability",
                    state,
                    drivers,
                    horizon=horizon,
                    seed=int(current_version.tick) * 1009 + horizon,
                    base_rate=float(actor.stability),
                )
                scenario_horizons[str(horizon)] = {
                    "expected": _expected_from_forecast(result),
                    "uncertainty": float(result["uncertainty"]),
                    "probabilities": result["probabilities"],
                }
            scenarios[scenario] = scenario_horizons
        scenario_matrix.append({
            "actor_id": actor.id,
            "actor_name": actor.name,
            "scenarios": scenarios,
        })

    effect_rows = (
        await session.execute(
            select(EffectModel)
            .where(EffectModel.simulation_id == simulation_id)
            .order_by(EffectModel.tick.desc(), EffectModel.id.desc())
            .limit(120)
        )
    ).scalars().all()

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for crisis_id, node in metadata.get("crisis_graph", {}).get("nodes", {}).items():
        if node.get("phase") == "resolved":
            continue
        crisis_key = f"crisis:{crisis_id}"
        nodes[crisis_key] = {
            "id": crisis_key,
            "kind": "crisis",
            "label": str(node.get("event_type") or crisis_id),
            "weight": clamp(node.get("intensity", 0.0)),
        }
        for actor_id in node.get("participants", []):
            actor_key = f"actor:{actor_id}"
            nodes.setdefault(actor_key, {
                "id": actor_key,
                "kind": "actor",
                "label": actor_id,
                "weight": 0.5,
            })
            edges.append({
                "source": crisis_key,
                "target": actor_key,
                "probability": clamp(
                    0.30
                    + float(node.get("intensity", 0.0)) * 0.40
                    + float(node.get("contagion", 0.0)) * 0.15
                ),
                "mechanism": "crisis_exposure",
            })

    grouped_effects: dict[tuple[str, str, str], list[EffectModel]] = defaultdict(list)
    for row in effect_rows:
        grouped_effects[(row.source, row.target, row.mechanism)].append(row)

    for (source, target, mechanism), rows in grouped_effects.items():
        source_key = f"actor:{source}"
        target_key = f"actor:{target}"
        nodes.setdefault(source_key, {
            "id": source_key, "kind": "actor", "label": source, "weight": 0.5,
        })
        nodes.setdefault(target_key, {
            "id": target_key, "kind": "actor", "label": target, "weight": 0.5,
        })
        confidence = sum(float(row.confidence) for row in rows) / len(rows)
        magnitude = min(1.0, sum(abs(float(row.delta)) for row in rows) * 8.0)
        edges.append({
            "source": source_key,
            "target": target_key,
            "probability": clamp(confidence * 0.70 + magnitude * 0.30),
            "mechanism": mechanism,
        })

    current_market = _market_stress(metadata)
    previous_market = _market_stress(previous_metadata) if previous_version else current_market
    current_crises = [
        node for node in metadata.get("crisis_graph", {}).get("nodes", {}).values()
        if node.get("phase") != "resolved"
    ]
    previous_crises = [
        node for node in previous_metadata.get("crisis_graph", {}).get("nodes", {}).values()
        if node.get("phase") != "resolved"
    ]

    calibration_rows = [
        item["calibration"] for item in actor_forecasts
        if item["calibration"]["mean_brier"] is not None
    ]
    aggregate_brier = (
        sum(float(item["mean_brier"]) for item in calibration_rows)
        / len(calibration_rows)
        if calibration_rows else None
    )

    return {
        "simulation_id": simulation_id,
        "tick": int(current_version.tick),
        "horizons": list(HORIZONS),
        "actors": actor_forecasts,
        "scenario_matrix": scenario_matrix,
        "causal_graph": {
            "nodes": list(nodes.values()),
            "edges": edges[:220],
        },
        "calibration": {
            "scored_targets": len(calibration_rows),
            "mean_brier": aggregate_brier,
            "quality": _calibration_quality(aggregate_brier),
        },
        "change_since_previous_snapshot": {
            "market_stress_delta": current_market - previous_market,
            "active_crises_delta": len(current_crises) - len(previous_crises),
            "previous_tick": int(previous_version.tick) if previous_version else None,
        },
        "model_version": "prediction-center-v1",
    }
