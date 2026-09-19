from app.strategic_dynamics import (
    bayesian_update,
    build_coalitions,
    get_belief,
    nash_bargain,
    pop_due_effects,
    schedule_delayed_effects,
    signal_profile,
    update_belief_from_action,
    update_forecast_calibration,
)


def test_bayesian_belief_update_moves_with_evidence():
    prior = 0.5
    posterior = bayesian_update(prior, evidence=0.9, reliability=0.8)
    assert posterior > prior


def test_action_updates_counterpart_belief():
    metadata = {}
    belief = update_belief_from_action(
        metadata,
        observer="B",
        counterpart="A",
        action_type="defensive_posture",
        information_quality=0.8,
        credibility=0.9,
        tick=3,
    )
    assert belief["threat"] > 0.5
    assert belief["cooperation"] < 0.5
    assert belief["last_updated_tick"] == 3
    assert get_belief(metadata, "B", "A") == belief


def test_signal_profile_is_deterministic():
    a = signal_profile("A", "public_statement", 0.7, 0.6, 42, 5)
    b = signal_profile("A", "public_statement", 0.7, 0.6, 42, 5)
    assert a == b
    assert 0.0 <= a["credibility"] <= 1.0


def test_delayed_effects_are_applied_only_when_due():
    metadata = {}
    created = schedule_delayed_effects(
        metadata,
        "A",
        "economic_adjustment",
        current_tick=2,
        source_action_id="act-1",
    )
    assert created
    assert pop_due_effects(metadata, 3) == []
    due = pop_due_effects(metadata, 5)
    assert len(due) == len(created)
    assert metadata["delayed_effects"] == []


def test_coalition_forms_from_shared_crisis_and_relationship():
    actors = {"A": {}, "B": {}, "C": {}}
    relationships = {
        "A:B": {"diplomatic": 0.4, "economic": 0.5},
        "B:A": {"diplomatic": 0.4, "economic": 0.5},
    }
    crisis_graph = {
        "nodes": {
            "c1": {
                "phase": "escalating",
                "participants": ["A", "B"],
            }
        }
    }
    coalitions = build_coalitions(actors, relationships, crisis_graph)
    assert any(set(item["members"]) == {"A", "B"} for item in coalitions)


def test_nash_bargain_requires_mutual_surplus():
    accepted = nash_bargain("A", "B", 0.8, 0.7, 0.2, 0.3)
    rejected = nash_bargain("A", "B", 0.2, 0.7, 0.3, 0.3)
    assert accepted.accepted is True
    assert accepted.surplus > 0
    assert rejected.accepted is False


def test_forecast_calibration_accumulates_brier_score():
    metadata = {}
    first = update_forecast_calibration(metadata, "A:stability", 0.8, True)
    second = update_forecast_calibration(metadata, "A:stability", 0.2, False)
    assert first["count"] == 2
    assert second["count"] == 2
    assert 0.0 <= second["mean_brier"] <= 1.0
