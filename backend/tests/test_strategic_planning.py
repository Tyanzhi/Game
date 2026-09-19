from app.strategic_planning import (
    evaluate_counterfactual,
    monte_carlo_action_value,
    plan_multi_horizon,
    repeated_game_state,
    update_strategy_learning,
)


def test_monte_carlo_action_value_is_deterministic():
    a = monte_carlo_action_value(
        "A", "defensive_posture", 0.65, 0.3, 8, 42,
        samples=32, crisis_intensity=0.6, market_stress=0.2, belief_uncertainty=0.4,
    )
    b = monte_carlo_action_value(
        "A", "defensive_posture", 0.65, 0.3, 8, 42,
        samples=32, crisis_intensity=0.6, market_stress=0.2, belief_uncertainty=0.4,
    )
    assert a == b
    assert 0.0 <= a.mean_utility <= 1.0
    assert a.downside <= a.upside


def test_multi_horizon_planner_returns_counterfactuals():
    options = [
        {"action": "observe", "expected_utility": 0.55, "risk": 0.05},
        {"action": "diplomatic_outreach", "expected_utility": 0.62, "risk": 0.18},
        {"action": "defensive_posture", "expected_utility": 0.60, "risk": 0.35},
    ]
    plan = plan_multi_horizon(
        "A",
        options,
        {"risk_tolerance": 0.5, "crisis_intensity": 0.4, "market_stress": 0.2},
        {"uncertainty": 0.3},
        {},
        seed=7,
        horizons=(3, 8, 20),
        samples=24,
    )
    assert plan["horizons"] == [3, 8, 20]
    assert plan["selected_action"] in {item["action"] for item in options}
    assert len(plan["aggregate"]) == len(options)
    assert len(plan["counterfactuals"]) == len(options) - 1


def test_counterfactual_can_prefer_alternative():
    result = evaluate_counterfactual(
        {"action": "observe", "mean_utility": 0.5, "variance": 0.03},
        {"action": "diplomatic_outreach", "mean_utility": 0.7, "variance": 0.02},
        risk_aversion=0.5,
    )
    assert result.preferred_under_model == "diplomatic_outreach"
    assert result.utility_delta > 0


def test_repeated_game_state_detects_conditional_cooperation():
    state = repeated_game_state(
        {"cooperation_count": 4, "pressure_count": 1, "trust": 0.8, "hostility": 0.1},
        {"cooperation": 0.8},
    )
    assert state.equilibrium_hint == "conditional_cooperation"
    assert state.cooperation_rate > state.retaliation_rate


def test_strategy_learning_moves_q_value_toward_outcome():
    metadata = {}
    first = update_strategy_learning(metadata, "A", "observe", 0.9, learning_rate=0.5)
    assert first["q_value"] > 0.5
    prior = first["q_value"]
    second = update_strategy_learning(metadata, "A", "observe", 0.1, learning_rate=0.5)
    assert second["q_value"] < prior
