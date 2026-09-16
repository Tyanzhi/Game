from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float: return max(lo, min(hi, float(v)))

@dataclass(frozen=True)
class FeedbackLoop:
    name: str
    source: str
    target: str
    coefficient: float

def propagate(state: dict[str,float], loops: Iterable[FeedbackLoop], iterations: int = 3) -> dict:
    values = dict(state)
    traces = []
    for i in range(max(1, iterations)):
        delta = {}
        for loop in loops:
            delta[loop.target] = delta.get(loop.target, 0.0) + values.get(loop.source, 0.0)*loop.coefficient
        for key, change in delta.items(): values[key] = clamp(values.get(key, 0.0) + change)
        traces.append({"iteration": i+1, "delta": delta})
    return {"state": values, "traces": traces}

def detect_tipping(state: dict[str,float], thresholds: dict[str,float] | None = None) -> list[str]:
    thresholds = thresholds or {}
    return sorted(key for key, threshold in thresholds.items() if state.get(key, 0.0) >= threshold)
