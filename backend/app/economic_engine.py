"""Deterministic macroeconomic state engine for WORLD ENGINE."""
from __future__ import annotations
from dataclasses import dataclass

def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))

@dataclass(frozen=True)
class EconomicResult:
    actor_id: str
    growth: float
    inflation: float
    resilience: float
    changes: dict

def run(states: dict[str, dict]) -> dict[str, EconomicResult]:
    out = {}
    for actor, s in states.items():
        capacity=clamp(s.get('economic_capacity',.5)); stability=clamp(s.get('stability',.5)); pressure=clamp(s.get('domestic_pressure',.3))
        growth=clamp(.35*capacity+.35*stability-.20*pressure)
        inflation=clamp(.25*pressure+.08*(1-capacity))
        resilience=clamp(.55*capacity+.30*stability-.15*pressure)
        out[actor]=EconomicResult(actor,growth,inflation,resilience,{'economic_capacity':(growth-capacity)*.05,'stability':(resilience-stability)*.03})
    return out
