"""Social-dynamics engine: pressure, unrest and cohesion."""
from __future__ import annotations
from dataclasses import dataclass

def clamp(v): return max(0.0,min(1.0,float(v)))
@dataclass(frozen=True)
class SocialResult:
    actor_id:str
    unrest:float
    cohesion:float
    changes:dict

def run(states:dict[str,dict]) -> dict[str,SocialResult]:
    out={}
    for actor,s in states.items():
        stability=clamp(s.get('stability',.5)); pressure=clamp(s.get('domestic_pressure',.3))
        unrest=clamp(.70*pressure+.30*(1-stability)); cohesion=clamp(.65*stability+.20*(1-pressure))
        out[actor]=SocialResult(actor,unrest,cohesion,{'stability':-unrest*.025,'domestic_pressure':unrest*.01})
    return out
