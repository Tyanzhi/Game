from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
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
    source_quality: float = 0.5
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
    metadata: dict | None = None


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


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _origin_key(event: RawEvent) -> str:
    raw = event.raw or {}
    domain = str(raw.get("domain") or "").strip().lower()
    if domain:
        return f"domain:{domain}"
    provider = str(raw.get("provider") or "").strip().lower()
    if provider:
        return f"provider:{provider}"
    return f"source:{event.source_id}"


def _confidence(group: list[RawEvent]) -> tuple[float, dict]:
    qualities = [_clamp(item.source_quality) for item in group]
    weights = [max(0.05, quality) for quality in qualities]
    weighted_prior = sum(
        _clamp(item.confidence) * weight
        for item, weight in zip(group, weights)
    ) / max(0.05, sum(weights))
    origin_keys = sorted({_origin_key(item) for item in group})
    independent_count = len(origin_keys)
    corroboration_bonus = min(0.18, max(0, independent_count - 1) * 0.05)
    final = min(0.99, weighted_prior + corroboration_bonus)
    return final, {
        "independent_source_count": independent_count,
        "origin_keys": origin_keys,
        "source_quality_mean": (
            sum(qualities) / len(qualities) if qualities else 0.0
        ),
        "weighted_prior_confidence": weighted_prior,
        "corroboration_bonus": corroboration_bonus,
        "confidence_model": "quality_weighted_corroboration_v1",
    }


def normalize(events: Iterable[RawEvent]) -> list[NormalizedEvent]:
    groups: list[list[RawEvent]] = []
    for event in events:
        for group in groups:
            if fingerprint(event) == fingerprint(group[0]) or _same_story(event, group[0]):
                group.append(event)
                break
        else:
            groups.append([event])
    result: list[NormalizedEvent] = []
    for group in groups:
        first = max(group, key=lambda item: item.timestamp)
        source_ids = tuple(sorted({item.source_id for item in group}))
        source_urls = tuple(sorted({item.source_url for item in group if item.source_url}))
        confidence, quality_metadata = _confidence(group)
        independent_count = int(quality_metadata["independent_source_count"])
        status = (
            "FACT"
            if (independent_count >= 2 and confidence >= 0.60)
            or confidence >= 0.85
            else "CLAIM"
        )
        source_records = []
        seen_source_records = set()
        for item in group:
            key = (item.source_id, item.source_url)
            if key in seen_source_records:
                continue
            seen_source_records.add(key)
            source_records.append({
                "source_id": item.source_id,
                "source_url": item.source_url,
                "source_quality": _clamp(item.source_quality),
                "source_confidence": _clamp(item.confidence),
                "origin_key": _origin_key(item),
            })
        metadata = {
            "raw_sources": [item.raw or {} for item in group],
            "source_records": source_records,
            "dedup_group_size": len(group),
            **quality_metadata,
        }
        result.append(NormalizedEvent(fingerprint(first), first.timestamp.astimezone(timezone.utc), tuple(sorted({a for item in group for a in item.actor_ids})), first.event_type, first.description or first.title, source_ids, len(source_ids), confidence, status if status in STATUSES else "HYPOTHESIS", source_urls, metadata))
    return sorted(result, key=lambda event: event.timestamp, reverse=True)
