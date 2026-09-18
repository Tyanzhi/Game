from types import SimpleNamespace

from app.event_propagation import EventPropagation


def event(kind="energy_disruption", actors=("A",), confidence=.9):
    return SimpleNamespace(event_id="evt-1", event_type=kind, actors=actors, confidence=confidence)


def test_same_seed_same_perception():
    actors = {
        "A": {"information_quality": .8, "energy_security": .3, "economic_capacity": .7, "trade_resilience": .6, "security_capacity": .7, "stability": .7, "strategic_patience": .5, "domestic_pressure": .2},
        "B": {"information_quality": .4, "energy_security": .9, "economic_capacity": .7, "trade_resilience": .8, "security_capacity": .7, "stability": .7, "strategic_patience": .5, "domestic_pressure": .2},
    }
    relationships = {"A:A": {"diplomatic": -.7}, "B:A": {"diplomatic": .7}}
    engine = EventPropagation()
    a = engine.propagate([event()], actors, relationships, seed=42)
    b = engine.propagate([event()], actors, relationships, seed=42)
    assert [(x.target, x.field, x.delta) for x in a] == [(x.target, x.field, x.delta) for x in b]


def test_different_actors_perceive_same_event_differently():
    actors = {
        "A": {"information_quality": .9, "energy_security": .2, "economic_capacity": .7, "trade_resilience": .6, "security_capacity": .7, "stability": .7, "strategic_patience": .5, "domestic_pressure": .2},
        "B": {"information_quality": .5, "energy_security": .9, "economic_capacity": .7, "trade_resilience": .8, "security_capacity": .7, "stability": .7, "strategic_patience": .5, "domestic_pressure": .2},
    }
    effects = EventPropagation().propagate([event()], actors, {}, seed=7)
    deltas = [x.delta for x in effects if x.field == "energy_security"]
    assert len(deltas) == 2
    assert deltas[0] != deltas[1]


def test_event_impacts_market_and_multiple_domains():
    effects = EventPropagation().propagate(
        [event("energy_disruption", ("A",), .9)],
        {"A": {"information_quality": .8, "energy_security": .7, "economic_capacity": .7, "trade_resilience": .7, "security_capacity": .7, "stability": .7, "strategic_patience": .5, "domestic_pressure": .2}},
        {},
        seed=1,
    )
    fields = {x.field for x in effects}
    assert "market:energy_price" in fields
    assert "market:global_trade" in fields
    assert "energy_security" in fields
    assert "economic_capacity" in fields
