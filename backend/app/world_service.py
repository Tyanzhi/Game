from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


TRACKED_FIELDS = {
    "stability",
    "economic_capacity",
    "diplomatic_capacity",
    "security_capacity",
    "domestic_pressure",
    "risk_tolerance",
    "strategic_patience",
    "escalation_threshold",
    "information_quality",
    "energy_security",
    "trade_resilience",
    "technological_capacity",
}


@dataclass
class WorldEvent:
    event_id: str
    event_type: str
    actor_ids: list[str]
    impact: dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0
    status: str = "FACT"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_payload(cls, payload: dict) -> "WorldEvent":
        return cls(
            event_id=str(payload["event_id"]),
            event_type=str(payload.get("event_type", "unknown")),
            actor_ids=[str(actor) for actor in payload.get("actor_ids", [])],
            impact={str(k): float(v) for k, v in payload.get("impact", {}).items()},
            confidence=max(0.0, min(1.0, float(payload.get("confidence", 1.0)))),
            status=str(payload.get("status", "FACT")),
        )


class WorldRuntime:
    """Canonical in-memory runtime used by the API and later simulation workers."""

    def __init__(self) -> None:
        self.tick = 0
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.actors: dict[str, dict] = {
            "usa": {"id": "usa", "name": "United States", "stability": 0.7, "economic_capacity": 0.8},
            "china": {"id": "china", "name": "China", "stability": 0.7, "economic_capacity": 0.8},
            "india": {"id": "india", "name": "India", "stability": 0.7, "economic_capacity": 0.7},
            "russia": {"id": "russia", "name": "Russia", "stability": 0.6, "economic_capacity": 0.6},
        }
        self._events: list[dict] = []

    def snapshot(self) -> dict:
        return {
            "tick": self.tick,
            "timestamp": self.timestamp,
            "actors": {key: dict(value) for key, value in self.actors.items()},
        }

    def apply_event(self, event: WorldEvent) -> dict:
        changes: dict[str, dict[str, float]] = {}
        for actor_id in event.actor_ids:
            actor = self.actors.setdefault(actor_id, {"id": actor_id, "name": actor_id})
            actor_changes = {}
            for field, delta in event.impact.items():
                if field not in TRACKED_FIELDS:
                    continue
                old = float(actor.get(field, 0.0))
                new = max(0.0, min(1.0, old + delta * event.confidence))
                actor[field] = new
                actor_changes[field] = new - old
            if actor_changes:
                changes[actor_id] = actor_changes
        self.tick += 1
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self._events.append({
            "event_id": event.event_id,
            "event_type": event.event_type,
            "actor_ids": event.actor_ids,
            "status": event.status,
            "confidence": event.confidence,
            "timestamp": self.timestamp,
            "changes": changes,
        })
        return {"event_id": event.event_id, "tick": self.tick, "changes": changes}

    def events(self) -> list[dict]:
        return list(self._events)
