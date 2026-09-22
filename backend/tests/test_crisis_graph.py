from types import SimpleNamespace

from app.crisis_graph import CrisisGraph


def make_event(kind="energy_disruption"):
    return SimpleNamespace(event_id="evt-1", event_type=kind, actors=("A", "B"), confidence=.9)


def actors():
    base = {
        "information_quality": .7,
        "economic_capacity": .7,
        "trade_resilience": .7,
        "energy_security": .7,
        "security_capacity": .7,
        "stability": .7,
        "strategic_patience": .5,
        "domestic_pressure": .2,
    }
    return {name: dict(base) for name in ("A", "B", "C")}


def test_crisis_lifecycle_is_deterministic():
    e = make_event()
    a, b = {}, {}
    g1 = CrisisGraph()
    g2 = CrisisGraph()
    for tick in range(1, 6):
        g1.advance(a, [e], actors(), {"C:A": {"diplomatic": .8}}, tick, 42)
        g2.advance(b, [e], actors(), {"C:A": {"diplomatic": .8}}, tick, 42)
    assert a == b


def test_crisis_can_contagiously_reach_connected_actor():
    state = {}
    g = CrisisGraph()
    g.advance(
        state,
        [make_event()],
        actors(),
        {"C:A": {"diplomatic": 1.0, "economic": 1.0}},
        1,
        2,
    )
    nodes = state["crisis_graph"]["nodes"]
    participants = next(iter(nodes.values()))["participants"]
    assert "C" in participants
    assert any(edge["mechanism"] == "crisis_contagion" for edge in state["crisis_graph"]["edges"])


def test_secondary_crisis_uses_parent_linkage():
    state = {}
    g = CrisisGraph()
    generated = []
    for tick in range(1, 15):
        generated.extend(g.advance(state, [make_event()], actors(), {}, tick, 99))
    if generated:
        assert generated[0].metadata["parent_crisis_id"]


def test_interacting_crises_create_compounding_edge():
    state = {}
    g = CrisisGraph()
    events = [
        SimpleNamespace(event_id="energy-1", event_type="energy_disruption", actors=("A",), confidence=.9),
        SimpleNamespace(event_id="econ-1", event_type="economic_crisis", actors=("A",), confidence=.9),
    ]
    g.advance(state, events, actors(), {}, 1, 11)
    assert any(
        edge["mechanism"] == "crisis_interaction"
        for edge in state["crisis_graph"]["edges"]
    )
    assert any(
        item.get("interaction_pressure", 0.0) > 0.0
        for item in state["crisis_graph"]["history"]
    )


def test_crisis_uncertainty_decays_with_repeated_observation():
    state = {}
    g = CrisisGraph()
    event = make_event()
    g.advance(state, [event], actors(), {}, 1, 7)
    node = next(iter(state["crisis_graph"]["nodes"].values()))
    first = float(node["uncertainty"])
    g.advance(state, [event], actors(), {}, 2, 7)
    second = float(node["uncertainty"])
    assert second <= first
    assert 0.0 <= second <= 1.0
