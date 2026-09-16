from backend.app.actor_decision import _risk, _utility

class Actor:
    risk_tolerance = 0.5
    escalation_threshold = 0.6
    information_quality = 0.7
    diplomatic_capacity = 0.8
    economic_capacity = 0.8
    security_capacity = 0.8
    domestic_pressure = 0.3


def test_risk_is_bounded():
    assert 0 <= _risk("defensive_posture", Actor(), 1.0) <= 1


def test_diplomatic_outreach_benefits_strained_relationship():
    utility_bad, _ = _utility("diplomatic_outreach", Actor(), .2, .2, .1, -.7)
    utility_good, _ = _utility("diplomatic_outreach", Actor(), .2, .2, .1, .7)
    assert utility_bad > utility_good
