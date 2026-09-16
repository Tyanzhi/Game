"""Energy-security engine with supply, demand and disruption effects."""
from __future__ import annotations
from dataclasses import dataclass

def clamp(v): return max(0.0,min(1.0,float(v)))
@dataclass(frozen=True)
class EnergyResult:
    actor_id:str
    security:float
    disruption:float
    changes:dict

def run(states:dict[str,dict]) -> dict[str,EnergyResult]:
    out={}
    for actor,s in states.items():
        capacity=clamp(s.get('economic_capacity',.5)); pressure=clamp(s.get('domestic_pressure',.3))
        security=clamp(.65*capacity+.20*(1-pressure)); disruption=clamp(.35*pressure+.20*(1-capacity))
        out[actor]=EnergyResult(actor,security,disruption,{'stability':(security-.5)*.02,'economic_capacity':-disruption*.01})
    return out
