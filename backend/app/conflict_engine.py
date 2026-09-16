"""Conflict engine: escalation pressure and de-escalation capacity."""
from __future__ import annotations
from dataclasses import dataclass

def clamp(v): return max(0.0,min(1.0,float(v)))
@dataclass(frozen=True)
class ConflictResult:
    actor_id:str
    escalation:float
    deescalation_capacity:float
    changes:dict

def run(states:dict[str,dict]) -> dict[str,ConflictResult]:
    out={}
    for actor,s in states.items():
        pressure=clamp(s.get('domestic_pressure',.3)); stability=clamp(s.get('stability',.5))
        escalation=clamp(.60*pressure+.25*(1-stability)); capacity=clamp(.55*stability+.25*(1-pressure))
        out[actor]=ConflictResult(actor,escalation,capacity,{'stability':-escalation*.015,'domestic_pressure':escalation*.006})
    return out
