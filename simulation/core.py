from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from random import Random
from typing import Dict, List


@dataclass
class Event:
    event_id: str
    event_type: str
    actor_ids: List[str]
    impact: Dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class ActorState:
    actor_id: str
    stability: float = 0.7
    economic_capacity: float = 0.7
    diplomatic_capacity: float = 0.7
    security_capacity: float = 0.7
    domestic_pressure: float = 0.3


@dataclass
class WorldState:
    tick: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    actors: Dict[str, ActorState] = field(default_factory=dict)
    events: List[Event] = field(default_factory=list)


class SimulationEngine:
    """Deterministic core. AI proposes actions; this engine applies validated effects."""

    def __init__(self, seed: int = 2026) -> None:
        self.rng = Random(seed)

    def apply_event(self, world: WorldState, event: Event) -> None:
        world.events.append(event)
        for actor_id in event.actor_ids:
            actor = world.actors.get(actor_id)
            if actor is None:
                continue
            actor.domestic_pressure = max(
                0.0, min(1.0, actor.domestic_pressure + event.impact.get("domestic_pressure", 0.0))
            )
            actor.stability = max(
                0.0, min(1.0, actor.stability + event.impact.get("stability", 0.0))
            )

    def tick(self, world: WorldState) -> WorldState:
        world.tick += 1
        world.timestamp = datetime.now(timezone.utc)
        for actor in world.actors.values():
            # Small bounded stochastic drift keeps the system dynamic without
            # allowing impossible values. Seeded RNG makes runs reproducible.
            drift = self.rng.uniform(-0.005, 0.005)
            actor.stability = max(0.0, min(1.0, actor.stability + drift))
            actor.domestic_pressure = max(0.0, min(1.0, actor.domestic_pressure - drift * 0.25))
        return world
