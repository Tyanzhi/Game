from app.strategic_foresight import (
    alliance_reliability,
    assess_multilateral_reliability,
    brinkmanship_state,
    build_scenario_tree,
    credible_commitment,
    resource_feasibility,
)


def test_scenario_tree_is_deterministic_and_normalized():
    a = build_scenario_tree("A", 0.7, 0.3, 0.4, seed=42, depth=3, branching=3)
    b = build_scenario_tree("A", 0.7, 0.3, 0.4, seed=42, depth=3, branching=3)
    assert a == b
    leaves = [node for node in a["nodes"] if node["depth"] == a["depth"]]
    assert abs(sum(node["probability"] for node in leaves) - 1.0) < 1e-9
    assert a["leaf_count"] == 27
    assert 0.0 <= a["escalation_probability"] <= 1.0


def test_resource_feasibility_detects_capacity_shortfall():
    low = resource_feasibility(
        "defensive_posture",
        {"economic_capacity": 0.02, "security_capacity": 0.05, "diplomatic_capacity": 0.5},
    )
    high = resource_feasibility(
        "defensive_posture",
        {"economic_capacity": 0.8, "security_capacity": 0.8, "diplomatic_capacity": 0.8},
    )
    assert low["feasible"] is False
    assert low["strain"] > 0
    assert high["feasible"] is True


def test_costly_commitment_can_be_credible():
    result = credible_commitment(
        {"economic_capacity": 0.8, "security_capacity": 0.8, "diplomatic_capacity": 0.8},
        signal_credibility=0.9,
        sunk_cost=0.6,
        domestic_pressure=0.1,
    )
    assert result["credible"] is True
    assert result["credibility"] >= 0.58


def test_brinkmanship_rises_with_risk_and_threat():
    high = brinkmanship_state(
        {"risk_tolerance": 0.9, "domestic_pressure": 0.6},
        {"risk_tolerance": 0.9, "domestic_pressure": 0.6},
        {"threat": 0.9},
        {"threat": 0.9},
    )
    low = brinkmanship_state(
        {"risk_tolerance": 0.2, "domestic_pressure": 0.1},
        {"risk_tolerance": 0.2, "domestic_pressure": 0.1},
        {"threat": 0.2},
        {"threat": 0.2},
    )
    assert high["escalation_risk"] > low["escalation_risk"]


def test_alliance_reliability_uses_memory_and_shared_crisis():
    relationships = {
        "A:B": {"diplomatic": 0.8, "economic": 0.7, "military": 0.6},
    }
    strong = alliance_reliability(
        "A", "B", relationships,
        {"trust": 0.9, "hostility": 0.0},
        shared_crisis=True,
    )
    weak = alliance_reliability(
        "A", "B", relationships,
        {"trust": 0.2, "hostility": 0.8},
        shared_crisis=False,
    )
    assert strong > weak


def test_multilateral_reliability_has_weakest_link():
    coalition = {"members": ["A", "B", "C"], "cohesion": 0.7}
    relationships = {
        "A:B": {"diplomatic": 0.8, "economic": 0.6, "military": 0.5},
        "A:C": {"diplomatic": 0.2, "economic": 0.2, "military": 0.1},
        "B:C": {"diplomatic": 0.5, "economic": 0.4, "military": 0.3},
    }
    memories = {
        "A:B": {"trust": 0.8, "hostility": 0.0},
        "A:C": {"trust": 0.3, "hostility": 0.4},
        "B:C": {"trust": 0.6, "hostility": 0.1},
    }
    crisis_graph = {
        "nodes": {
            "crisis-1": {
                "phase": "escalating",
                "participants": ["A", "B", "C"],
            }
        }
    }
    result = assess_multilateral_reliability(
        coalition, relationships, memories, crisis_graph
    )
    assert 0.0 <= result["reliability"] <= 1.0
    assert result["weakest_link"] is not None
