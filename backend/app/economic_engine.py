from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))

@dataclass(frozen=True)
class EconomicState:
    output: float
    inflation: float
    unemployment: float
    debt: float
    reserves: float
    resilience: float

def step(state: EconomicState, *, shock: float = 0.0, trade_shock: float = 0.0, energy_shock: float = 0.0, policy: float = 0.0):
    growth = 0.01 + 0.02*state.resilience - 0.025*shock - 0.015*trade_shock - 0.012*energy_shock + 0.008*policy
    inflation = clamp(state.inflation + 0.035*energy_shock + 0.02*trade_shock - 0.01*policy)
    unemployment = clamp(state.unemployment - 0.015*growth + 0.02*shock + 0.01*trade_shock)
    debt = clamp(state.debt + max(0.0, -growth)*0.04 - max(0.0, growth)*0.015)
    reserves = clamp(state.reserves - 0.025*energy_shock - 0.015*trade_shock + 0.01*policy)
    output = max(0.0, state.output*(1.0 + growth))
    new = EconomicState(output, inflation, unemployment, debt, reserves, clamp(state.resilience - 0.01*shock - 0.008*trade_shock + 0.004*policy))
    return new, {"growth": growth, "inflation_change": inflation-state.inflation, "unemployment_change": unemployment-state.unemployment, "debt_change": debt-state.debt, "reserves_change": reserves-state.reserves}

def simulate(states: Mapping[str, EconomicState], shocks: Mapping[str, Mapping[str, float]] | None = None) -> dict[str, dict]:
    shocks = shocks or {}
    return {aid: {"state": (lambda r: r[0].__dict__)(step(states[aid], **shocks.get(aid, {}))), "effects": step(states[aid], **shocks.get(aid, {}))[1]} for aid in sorted(states)}
