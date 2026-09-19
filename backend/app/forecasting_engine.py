"""Probabilistic ensemble forecaster for WORLD ENGINE."""
from __future__ import annotations

import hashlib
import math


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _stable_noise(target: str, seed: int, scale: float = 0.02) -> float:
    digest = int(hashlib.sha256(f"{target}:{seed}".encode()).hexdigest()[:8], 16)
    unit = digest / 0xFFFFFFFF
    return (unit - 0.5) * 2.0 * scale


def _normalize(values: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in values.values()) or 1.0
    return {key: max(0.0, value) / total for key, value in values.items()}


def _entropy(probabilities: dict[str, float]) -> float:
    entropy = 0.0
    for probability in probabilities.values():
        if probability > 0:
            entropy -= probability * math.log(probability, 3)
    return clamp(entropy)


def _bayesian_mean(prior_mean: float, evidence: float, evidence_weight: float) -> float:
    prior_strength = 6.0
    alpha = max(0.001, prior_mean * prior_strength)
    beta = max(0.001, (1.0 - prior_mean) * prior_strength)
    evidence_probability = clamp(0.5 + evidence)
    evidence_strength = max(0.0, evidence_weight) * 4.0
    alpha += evidence_probability * evidence_strength
    beta += (1.0 - evidence_probability) * evidence_strength
    return clamp(alpha / (alpha + beta))


def forecast(
    target: str,
    state: dict,
    drivers: dict,
    horizon: int = 5,
    seed: int = 1,
    base_rate: float | None = None,
) -> dict:
    field = target.split(":")[-1]
    current = clamp(state.get(field, state.get("stability", 0.5)))
    prior = clamp(base_rate if base_rate is not None else current)

    driver_values = [float(value) for value in drivers.values()]
    signal = sum(driver_values)
    evidence_weight = min(1.0, sum(abs(value) for value in driver_values))

    # Three deliberately different forecasting components.
    base_rate_model = prior
    trend_model = clamp(current + max(-0.18, min(0.18, signal * 0.10)))
    bayesian_model = _bayesian_mean(prior, signal * 0.12, evidence_weight)

    horizon_penalty = min(0.18, max(0, int(horizon) - 1) * 0.012)
    ensemble_high = clamp(
        base_rate_model * 0.30
        + trend_model * 0.35
        + bayesian_model * 0.35
        + _stable_noise(target, seed)
    )

    dispersion = max(
        base_rate_model,
        trend_model,
        bayesian_model,
    ) - min(base_rate_model, trend_model, bayesian_model)

    center_distance = abs(ensemble_high - 0.5)
    raw = {
        "low": clamp((1.0 - ensemble_high) * (0.72 + center_distance * 0.22)),
        "medium": clamp(0.42 - center_distance * 0.48 + dispersion * 0.35),
        "high": clamp(ensemble_high * (0.72 + center_distance * 0.22)),
    }
    probabilities = _normalize(raw)

    uncertainty = clamp(
        0.18
        + _entropy(probabilities) * 0.38
        + dispersion * 0.45
        + horizon_penalty
        + (1.0 - evidence_weight) * 0.10
    )

    return {
        "target": target,
        "horizon": int(horizon),
        "probabilities": probabilities,
        "drivers": list(drivers),
        "uncertainty": uncertainty,
        "model_version": "forecast-v2",
        "ensemble": {
            "base_rate": base_rate_model,
            "trend": trend_model,
            "bayesian_update": bayesian_model,
            "dispersion": dispersion,
        },
        "calibration": {
            "scoring_rule": "brier",
            "status": "pending_observed_outcome",
        },
    }


def brier_score(probability: float, outcome: bool) -> float:
    """Binary Brier score; lower is better."""
    p = clamp(probability)
    observed = 1.0 if outcome else 0.0
    return (p - observed) ** 2
