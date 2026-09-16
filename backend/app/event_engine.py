from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
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
    raw: dict | None = None


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
    source_urls: tuple[str, ...] = ()


def _canonical(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    return set(_canonical(text).split())


def fingerprint(event: RawEvent) -> str:
    title = _canonical(event.title)
    actors = ",".join(sorted(event.actor_ids))
    day = event.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")
    basis = "|".join([event.event_type, title, actors, day])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def _same_story(a: RawEvent, b: RawEvent) -> bool:
    if a.event_type != b.event_type:
        return False
    if set(a.actor_ids) and set(b.actor_ids) and not (set(a.actor_ids) & set(b.actor_ids)):
        return False
    ta, tb = _tokens(a.title), _tokens(b.title)
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    similarity = SequenceMatcher(None, _canonical(a.title), _canonical(b.title)).ratio()
    delta_hours = abs((a.timestamp - b.timestamp).total_seconds()) / 3600
    return delta_hours <= 72 and (jaccard >= 0.55 or similarity >= 0.78)


def normalize(events: Iterable[RawEvent]) -> list[NormalizedEvent]:
    groups: list[list[RawEvent]] = []
    for event in events:
        placed = False
        for group in groups:
            if fingerprint(event) == fingerprint(group[0]) or _same_story(event, group[0]):
                group.append(event)
                placed = True
                break
        if not placed:
            groups.append([event])

    result: list[NormalizedEvent] = []
    for group in groups:
        first = max(group, key=lambda item: item.timestamp)
        ids = sorted({fingerprint(item) for item in group})
        event_id = ids[0] if ids else fingerprint(first)
        source_ids = tuple(sorted({item.source_id for item in group}))
        confidence = min(0.99, max(item.confidence for item in group) + 0.05 * max(0, len(source_ids) - 1))
        status = "FACT" if len(source_ids) >= 2 or confidence >= 0.75 else "CLAIM"
        result.append(NormalizedEvent(
            event_id=event_id,
            timestamp=first.timestamp.astimezone(timezone.utc),
            actors=tuple(sorted({a for item in group for a in item.actor_ids})),
            event_type=first.event_type,
            description=first.description or first.title,
            source_ids=source_ids,
            source_count=len(source_ids),
            confidence=confidence,
            status=status if status in STATUSES else "HYPOTHESIS",
            source_urls=tuple(sorted({item.source_url for item in group if item.source_url})),
        ))
    return sorted(result, key=lambda event: event.timestamp, reverse=True)
