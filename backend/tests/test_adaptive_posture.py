from app.decision_engine import _strategic_posture


def test_adaptive_postures_cover_containment_exploitation_and_diversion():
    theory = {"liberalism": 0.4, "constructivism": 0.4}

    assert _strategic_posture(
        "defensive_posture",
        theory,
        own_crisis=0.72,
        target_crisis=0.20,
        risk_tolerance=0.50,
        domestic_pressure=0.30,
    ) == "containment"

    assert _strategic_posture(
        "economic_adjustment",
        theory,
        own_crisis=0.20,
        target_crisis=0.74,
        risk_tolerance=0.70,
        domestic_pressure=0.25,
    ) == "opportunistic_leverage"

    assert _strategic_posture(
        "public_statement",
        theory,
        own_crisis=0.20,
        target_crisis=0.30,
        risk_tolerance=0.55,
        domestic_pressure=0.78,
    ) == "diversion"


def test_cooperative_mediation_remains_available():
    theory = {"liberalism": 0.70, "constructivism": 0.60}
    assert _strategic_posture(
        "diplomatic_outreach",
        theory,
        own_crisis=0.20,
        target_crisis=0.20,
        risk_tolerance=0.40,
        domestic_pressure=0.30,
    ) == "cooperative_mediation"
