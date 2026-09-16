from __future__ import annotations
import math
from hashlib import sha256

def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float: return max(lo, min(hi, float(v)))

def _sigmoid(x: float) -> float: return 1.0/(1.0+math.exp(-max(-20.0,min(20.0,x))))

def forecast(target: str, state: dict[str,float], drivers: dict[str,float], horizon: int = 5, seed: int = 0) -> dict:
    score = sum(float(v) for v in drivers.values()) + 0.5*sum(float(v) for v in state.values())
    probability = _sigmoid(score / max(1.0, len(drivers)+len(state)))
    uncertainty = clamp(0.55 - 0.05*math.log1p(max(0,horizon)) + 0.15*(1.0-probability))
    fingerprint = sha256(f"{target}|{horizon}|{seed}|{sorted(state.items())}|{sorted(drivers.items())}".encode()).hexdigest()[:16]
    return {"target": target, "horizon": horizon, "probabilities": {"occurs": probability, "does_not_occur": 1.0-probability}, "drivers": sorted(drivers), "uncertainty": uncertainty, "model_version": "deterministic-v1", "fingerprint": fingerprint}

def scenario_forecast(target: str, base_state: dict[str,float], scenarios: dict[str,dict[str,float]], horizon: int = 5, seed: int = 0) -> dict[str,dict]:
    return {name: forecast(target, base_state, values, horizon, seed) for name, values in sorted(scenarios.items())}
