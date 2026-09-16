"""Complex-systems layer: bounded feedback, momentum and tipping-risk signals."""
from __future__ import annotations
from dataclasses import dataclass

def clamp(v): return max(0.0,min(1.0,float(v)))
@dataclass(frozen=True)
class ComplexState:
    stability:float
    pressure:float
    feedback:float
    tipping_risk:float

def step(state:dict) -> ComplexState:
    stability=clamp(state.get('stability',.5)); pressure=clamp(state.get('domestic_pressure',.3))
    feedback=clamp(.55*pressure+.35*(1-stability))
    tipping=clamp(max(0.0,feedback-.55)*2.0)
    return ComplexState(stability,pressure,feedback,tipping)
