from __future__ import annotations
from dataclasses import dataclass

def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float: return max(lo, min(hi, float(v)))

@dataclass(frozen=True)
class EnergyState:
    supply: float
    demand: float
    storage: float
    import_dependency: float
    diversification: float

def step(state: EnergyState, *, supply_shock: float = 0.0, demand_shock: float = 0.0) -> tuple[EnergyState, dict]:
    shock = clamp(supply_shock)
    supply = clamp(state.supply - shock*(1.0-state.diversification) + 0.01*state.storage)
    demand = clamp(state.demand + demand_shock)
    storage = clamp(state.storage + 0.02*(supply-demand) - 0.02*shock)
    security = clamp(supply/(0.1+demand))
    return EnergyState(supply, demand, storage, state.import_dependency, state.diversification), {"energy_security": security, "supply_change": supply-state.supply, "storage_change": storage-state.storage}
