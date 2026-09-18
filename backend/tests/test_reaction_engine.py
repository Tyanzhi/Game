from __future__ import annotations

import asyncio

from app.cascade_engine import CascadeEngine, Effect
from app.reaction_engine import plan_reactions


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, actors, relationships):
        self.actors = actors
        self.relationships = relationships
        self.added = []

    async def execute(self, query):
        # The reaction engine uses two select patterns: all actors and one relationship.
        sql = str(query)
        if "FROM actors" in sql:
            return _ScalarResult(self.actors)
        params = query.compile().params
        source = params.get("source_actor_id_1")
        target = params.get("target_actor_id_1")
        for rel in self.relationships:
            if rel.source_actor_id == source and rel.target_actor_id == target:
                return _ScalarResult([rel])
        return _ScalarResult([])

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


class Actor:
    def __init__(self, id, domestic_pressure=.2, strategic_patience=.5,
                 escalation_threshold=.6, information_quality=.7, economic_capacity=.7):
        self.id = id
        self.domestic_pressure = domestic_pressure
        self.strategic_patience = strategic_patience
        self.escalation_threshold = escalation_threshold
        self.information_quality = information_quality
        self.economic_capacity = economic_capacity


class Relationship:
    def __init__(self, source_actor_id, target_actor_id, diplomatic):
        self.source_actor_id = source_actor_id
        self.target_actor_id = target_actor_id
        self.diplomatic = diplomatic


def test_cascade_propagates_to_third_actor():
    effects = [Effect("A", "B", "stability", -0.1)]
    result, truncated = CascadeEngine(max_depth=2).run(
        effects,
        {"B": ["A", "C"], "C": ["A", "B"]},
    )
    assert truncated is False
    assert [(e.source, e.target, e.depth) for e in result] == [
        ("A", "B", 0),
        ("B", "C", 1),
    ]


def test_reactions_are_deterministic_for_same_seed():
    actors = [
        Actor("A"),
        Actor("B", domestic_pressure=.5, strategic_patience=.2, escalation_threshold=.5),
        Actor("C"),
    ]
    relationships = [Relationship("B", "A", -0.6), Relationship("C", "B", 0.2)]
    actions = [{
        "action_id": "action-1",
        "actor_id": "A",
        "status": "executed",
        "effects": {"target_actor_id": "B", "diplomatic_delta": -0.025},
    }]

    first = asyncio.run(plan_reactions(_Session(actors, relationships), actions, "sim", 42, third_party_rate=1.0, shock_rate=1.0))
    second = asyncio.run(plan_reactions(_Session(actors, relationships), actions, "sim", 42, third_party_rate=1.0, shock_rate=1.0))

    first_signature = (
        [(row["actor_id"], row["action"], row["target_actor_id"], row["reason"]) for row in first[0]],
        first[1],
    )
    second_signature = (
        [(row["actor_id"], row["action"], row["target_actor_id"], row["reason"]) for row in second[0]],
        second[1],
    )
    assert first_signature == second_signature


def test_third_party_intervention_is_generated():
    actors = [Actor("A"), Actor("B"), Actor("C")]
    relationships = [Relationship("C", "B", 0.1)]
    actions = [{
        "action_id": "action-1",
        "actor_id": "A",
        "status": "executed",
        "effects": {"target_actor_id": "B", "diplomatic_delta": 0.025},
    }]

    reactions, _ = asyncio.run(
        plan_reactions(_Session(actors, relationships), actions, "sim", 7, third_party_rate=1.0, shock_rate=0.0)
    )
    assert len(reactions) == 2
    assert any(row["actor_id"] == "C" and row["reason"] == "third_party_intervention" for row in reactions)


def test_unexpected_shock_is_generated_when_rate_is_one():
    actors = [Actor("A"), Actor("B")]
    reactions, shocks = asyncio.run(
        plan_reactions(_Session(actors, []), [], "sim", 7, third_party_rate=0.0, shock_rate=1.0)
    )
    assert reactions == []
    assert len(shocks) == 1
    assert shocks[0]["mechanism"] == "unexpected_shock"
    assert shocks[0]["target"] in {"A", "B"}
