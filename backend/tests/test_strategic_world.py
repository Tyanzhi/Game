from app.forecasting_engine import brier_score, forecast
from app.ir_theory import assess_ir_lenses, theory_adjustment
from app.strategic_memory import decay_memory, get_memory, update_memory_from_action


def test_ir_lenses_shift_action_scores():
    actor = {
        "security_capacity": 0.45,
        "economic_capacity": 0.8,
        "stability": 0.7,
        "domestic_pressure": 0.35,
        "strategic_patience": 0.7,
    }
    relationship = {
        "diplomatic": -0.7,
        "economic": 0.8,
        "trade": 0.9,
        "military": 0.5,
    }
    assessment = assess_ir_lenses(
        actor,
        relationship,
        {"trust": 0.3, "hostility": 0.6, "norm_alignment": 0.5},
        crisis_intensity=0.8,
        markets={"financial_stress": 0.3, "global_trade": -0.4},
    )
    assert 0.0 <= assessment.realism <= 1.0
    assert 0.0 <= assessment.liberalism <= 1.0
    assert theory_adjustment("defensive_posture", assessment) != theory_adjustment("diplomatic_outreach", assessment)


def test_strategic_memory_updates_and_decays():
    metadata = {}
    before = dict(get_memory(metadata, "B", "A"))
    after = update_memory_from_action(metadata, "B", "A", "diplomatic_outreach")
    assert after["trust"] > before["trust"]
    assert after["cooperation_count"] == 1

    hostile = update_memory_from_action(metadata, "B", "A", "defensive_posture")
    assert hostile["hostility"] > 0.0

    old_hostility = hostile["hostility"]
    decay_memory(metadata, rate=0.1)
    assert get_memory(metadata, "B", "A")["hostility"] < old_hostility


def test_forecast_v2_is_deterministic_and_normalized():
    state = {"stability": 0.65}
    drivers = {"economic": -0.08, "social": -0.05}
    a = forecast("A:stability", state, drivers, horizon=5, seed=42)
    b = forecast("A:stability", state, drivers, horizon=5, seed=42)

    assert a == b
    assert a["model_version"] == "forecast-v2"
    assert abs(sum(a["probabilities"].values()) - 1.0) < 1e-9
    assert a["calibration"]["scoring_rule"] == "brier"
    assert set(a["ensemble"]) == {"base_rate", "trend", "bayesian_update", "dispersion"}


def test_brier_score_rewards_better_probability():
    assert brier_score(0.9, True) < brier_score(0.6, True)
    assert brier_score(0.1, False) < brier_score(0.4, False)
