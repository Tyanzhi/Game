from __future__ import annotations
from dataclasses import dataclass

def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float: return max(lo, min(hi, float(v)))

@dataclass(frozen=True)
class SocialState:
    trust: float
    polarization: float
    protest_pressure: float
    cohesion: float
    migration_pressure: float

def step(state: SocialState, *, economic_stress: float = 0.0, shock: float = 0.0, institutional_response: float = 0.0) -> tuple[SocialState, dict]:
    protest = clamp(state.protest_pressure + 0.16*economic_stress + 0.10*shock - 0.12*institutional_response)
    polarization = clamp(state.polarization + 0.08*shock + 0.05*economic_stress - 0.04*institutional_response)
    trust = clamp(state.trust - 0.08*economic_stress - 0.05*shock + 0.07*institutional_response)
    cohesion = clamp(state.cohesion + 0.05*trust - 0.05*polarization - 0.03*protest)
    migration = clamp(state.migration_pressure + 0.10*economic_stress + 0.08*shock - 0.03*trust)
    new = SocialState(trust, polarization, protest, cohesion, migration)
    return new, {"trust_change": trust-state.trust, "polarization_change": polarization-state.polarization, "protest_change": protest-state.protest_pressure, "cohesion_change": cohesion-state.cohesion, "migration_change": migration-state.migration_pressure}
