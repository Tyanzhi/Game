from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


STATUSES = {"FACT", "CLAIM", "HYPOTHESIS"}


@dataclass(frozen=True)
class RawEvent:
    source_id: str
    source_url: str
    title: str
    description: str
    timestamp: datetime
    actor_ids: tuple[str, ...] = ()
    event_type: str = "unknown"
    confidence: float = 0.5


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    timestamp: datetime
    actors: tuple[str, ...]
    event_type: str
    description: str
    source_ids: tuple[str, ...]
    source_count: int
    confidence: float
    status: str


def _canonical(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def fingerprint(event: RawEvent) -> str:
    basis = "|".join(
        [event.event_type, _canonical(event.title), ",".join(sorted(event.actor_ids)), event.timestamp.strftime("%Y-%m-%d")]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def normalize(events: Iterable[RawEvent]) -> list[NormalizedEvent]:
    groups: dict[str, list[RawEvent]] = {}
    for event in events:
        groups.setdefault(fingerprint(event), []).append(event)

    result: list[NormalizedEvent] = []
    for event_id, group in groups.items():
        first = max(group, key=lambda item: item.timestamp)
        confidence = min(0.99, max(item.confidence for item in group) + 0.05 * (len(group) - 1))
        status = "FACT" if len(group) >= 2 else ("CLAIM" if first.confidence < 0.75 else "FACT")
        result.append(
            NormalizedEvent(
                event_id=event_id,
                timestamp=first.timestamp.astimezone(timezone.utc),
                actors=tuple(sorted(set(a for item in group for a in item.actor_ids))),
                event_type=first.event_type,
                description=first.description,
                source_ids=tuple(sorted({item.source_id for item in group})),
                source_count=len(group),
                confidence=confidence,
                status=status if status in STATUSES else "HYPOTHESIS",
            )
        )
    return result
