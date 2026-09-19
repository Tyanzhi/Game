from __future__ import annotations

from dataclasses import dataclass


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


@dataclass(frozen=True)
class TheoryAssessment:
    realism: float
    liberalism: float
    constructivism: float
    complex_interdependence: float
    security_dilemma: float

    def as_dict(self) -> dict[str, float]:
        return {
            "realism": self.realism,
            "liberalism": self.liberalism,
            "constructivism": self.constructivism,
            "complex_interdependence": self.complex_interdependence,
            "security_dilemma": self.security_dilemma,
        }


def assess_ir_lenses(
    actor: dict,
    relationship: dict | None = None,
    memory: dict | None = None,
    crisis_intensity: float = 0.0,
    markets: dict | None = None,
) -> TheoryAssessment:
    relationship = relationship or {}
    memory = memory or {}
    markets = markets or {}

    diplomatic = float(relationship.get("diplomatic", 0.0))
    economic_link = abs(float(relationship.get("economic", 0.0)))
    trade_link = abs(float(relationship.get("trade", 0.0)))
    military_link = float(relationship.get("military", 0.0))

    security = clamp(actor.get("security_capacity", 0.5))
    economy = clamp(actor.get("economic_capacity", 0.5))
    stability = clamp(actor.get("stability", 0.5))
    pressure = clamp(actor.get("domestic_pressure", 0.2))
    patience = clamp(actor.get("strategic_patience", 0.5))

    remembered_trust = clamp(memory.get("trust", 0.5))
    remembered_hostility = clamp(memory.get("hostility", 0.0))
    norm_alignment = clamp(memory.get("norm_alignment", 0.5))

    financial_stress = clamp(markets.get("financial_stress", 0.0))
    global_trade_stress = clamp(abs(markets.get("global_trade", 0.0)))

    realism = clamp(
        0.30
        + crisis_intensity * 0.30
        + max(0.0, -diplomatic) * 0.18
        + max(0.0, military_link) * 0.10
        + pressure * 0.08
        + (1.0 - security) * 0.12
    )
    liberalism = clamp(
        0.22
        + max(0.0, diplomatic) * 0.16
        + economic_link * 0.18
        + trade_link * 0.18
        + patience * 0.10
        + remembered_trust * 0.10
        - financial_stress * 0.08
    )
    constructivism = clamp(
        0.20
        + norm_alignment * 0.32
        + remembered_trust * 0.14
        - remembered_hostility * 0.18
        + stability * 0.08
    )
    complex_interdependence = clamp(
        0.15
        + economic_link * 0.28
        + trade_link * 0.28
        + economy * 0.08
        + global_trade_stress * 0.08
    )
    security_dilemma = clamp(
        0.10
        + crisis_intensity * 0.28
        + max(0.0, -diplomatic) * 0.24
        + max(0.0, military_link) * 0.18
        + (1.0 - remembered_trust) * 0.12
    )

    return TheoryAssessment(
        realism=realism,
        liberalism=liberalism,
        constructivism=constructivism,
        complex_interdependence=complex_interdependence,
        security_dilemma=security_dilemma,
    )


ACTION_THEORY_WEIGHTS = {
    "observe": {
        "realism": 0.04,
        "liberalism": 0.02,
        "constructivism": 0.04,
        "complex_interdependence": 0.02,
        "security_dilemma": -0.01,
    },
    "diplomatic_outreach": {
        "realism": -0.02,
        "liberalism": 0.16,
        "constructivism": 0.11,
        "complex_interdependence": 0.12,
        "security_dilemma": -0.08,
    },
    "economic_adjustment": {
        "realism": 0.05,
        "liberalism": 0.06,
        "constructivism": 0.00,
        "complex_interdependence": 0.14,
        "security_dilemma": 0.01,
    },
    "defensive_posture": {
        "realism": 0.18,
        "liberalism": -0.06,
        "constructivism": -0.02,
        "complex_interdependence": -0.04,
        "security_dilemma": 0.15,
    },
    "public_statement": {
        "realism": 0.03,
        "liberalism": 0.05,
        "constructivism": 0.14,
        "complex_interdependence": 0.03,
        "security_dilemma": 0.02,
    },
}


def theory_adjustment(action: str, assessment: TheoryAssessment) -> float:
    weights = ACTION_THEORY_WEIGHTS.get(action, {})
    values = assessment.as_dict()
    return sum(values.get(name, 0.0) * weight for name, weight in weights.items())
