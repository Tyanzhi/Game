from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .event_engine import NormalizedEvent
from .models import ActorModel, EventModel, EventSourceModel, SimulationRunModel, SimulationTickModel, WorldSnapshotModel

def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

async def _persist_event_sources(
    session: AsyncSession,
    event_id: str,
    metadata: dict,
    fallback_source_ids: tuple[str, ...],
    fallback_urls: tuple[str, ...],
    source_title: str,
) -> None:
    existing_rows = (
        await session.execute(
            select(EventSourceModel).where(EventSourceModel.event_id == event_id)
        )
    ).scalars().all()
    existing_pairs = {
        (row.source_id, row.source_url)
        for row in existing_rows
    }

    records = metadata.get("source_records")
    if not isinstance(records, list) or not records:
        records = [
            {
                "source_id": source_id,
                "source_url": (
                    fallback_urls[index]
                    if index < len(fallback_urls)
                    else (fallback_urls[0] if fallback_urls else "")
                ),
            }
            for index, source_id in enumerate(fallback_source_ids)
        ]

    for record in records:
        if not isinstance(record, dict):
            continue
        source_id = str(record.get("source_id") or "").strip()
        source_url = str(record.get("source_url") or "").strip()
        if not source_id:
            continue
        pair = (source_id, source_url)
        if pair in existing_pairs:
            continue
        session.add(EventSourceModel(
            event_id=event_id,
            source_id=source_id,
            source_url=source_url,
            source_title=source_title[:500],
            raw_json=record,
        ))
        existing_pairs.add(pair)


async def persist_events(session: AsyncSession, events: list[NormalizedEvent]) -> tuple[int, int]:
    new_count = duplicate_count = 0
    for event in events:
        existing = await session.get(EventModel, event.event_id)
        if existing:
            duplicate_count += 1
            existing.source_count = max(existing.source_count, event.source_count)
            existing.confidence = max(existing.confidence, event.confidence)
            existing.status = event.status
            metadata = existing.metadata_json if isinstance(existing.metadata_json, dict) else {}
            metadata.update(event.metadata or {})
            metadata["source_urls"] = list(event.source_urls)
            metadata["actors"] = list(event.actors)
            existing.metadata_json = metadata
            await _persist_event_sources(
                session,
                event.event_id,
                metadata,
                event.source_ids,
                event.source_urls,
                event.description,
            )
            continue
        metadata = dict(event.metadata or {})
        metadata["source_urls"] = list(event.source_urls)
        metadata["actors"] = list(event.actors)
        session.add(EventModel(id=event.event_id, event_type=event.event_type, title=event.description[:500], description=event.description, event_timestamp=event.timestamp, confidence=event.confidence, status=event.status, source_count=event.source_count, metadata_json=metadata))
        await session.flush()
        await _persist_event_sources(
            session,
            event.event_id,
            metadata,
            event.source_ids,
            event.source_urls,
            event.description,
        )
        new_count += 1
    await session.flush()
    return new_count, duplicate_count

async def apply_events(session: AsyncSession, events: list[NormalizedEvent]) -> dict:
    changes: dict[str, dict[str, float]] = {}
    for event in events:
        for actor_id in event.actors:
            actor = await session.get(ActorModel, actor_id)
            if not actor:
                continue
            delta = (event.confidence - 0.5) * 0.04
            if event.event_type in {"conflict", "protest", "sanction"}:
                actor.domestic_pressure = clamp(actor.domestic_pressure + abs(delta))
                actor.stability = clamp(actor.stability - abs(delta) * 0.5)
            changes[actor_id] = {"stability": actor.stability, "domestic_pressure": actor.domestic_pressure}
    return changes

async def create_snapshot(session: AsyncSession, simulation_id: str, tick: int, changes: dict, event_ids: list[str] | None = None) -> None:
    ids = event_ids or []
    state = {"actor_changes": changes, "event_ids": ids}
    session.add(WorldSnapshotModel(tick=tick, simulation_id=simulation_id, model_version="world-state-v1", dataset_version="live", random_seed=0, state_json=state))
    session.add(SimulationTickModel(simulation_id=simulation_id, tick=tick, event_ids=ids, state_changes=changes))

async def create_run(session: AsyncSession, run_id: str, query: str) -> SimulationRunModel:
    run = SimulationRunModel(id=run_id, query=query)
    session.add(run)
    await session.flush()
    return run

async def finish_run(session: AsyncSession, run: SimulationRunModel, raw: int, new: int, dedup: int) -> None:
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    run.events_ingested, run.events_new, run.events_deduplicated = raw, new, dedup
