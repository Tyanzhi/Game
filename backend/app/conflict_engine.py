from __future__ import annotations
from dataclasses import dataclass

def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float: return max(lo, min(hi, float(v)))

@dataclass(frozen=True)
class ConflictState:
    tension: float
    escalation: float
    deterrence: float
    readiness: float
    negotiation: float

def step(state: ConflictState, *, hostile_signal: float = 0.0, deterrence_signal: float = 0.0, negotiation_signal: float = 0.0, uncertainty: float = 0.0) -> tuple[ConflictState, dict]:
    escalation = clamp(state.escalation + 0.20*hostile_signal + 0.08*uncertainty - 0.16*deterrence_signal - 0.18*negotiation_signal)
    tension = clamp(state.tension + 0.16*escalation + 0.08*hostile_signal - 0.10*negotiation_signal)
    deterrence = clamp(state.deterrence + 0.05*deterrence_signal - 0.03*escalation)
    negotiation = clamp(state.negotiation + 0.08*negotiation_signal - 0.04*hostile_signal)
    new = ConflictState(tension, escalation, deterrence, state.readiness, negotiation)
    phase = "de-escalation" if escalation < 0.35 else "competition" if escalation < 0.65 else "acute_crisis" if escalation < 0.85 else "critical"
    return new, {"phase": phase, "tension_change": tension-state.tension, "escalation_change": escalation-state.escalation, "deterrence_change": deterrence-state.deterrence, "negotiation_change": negotiation-state.negotiation}
