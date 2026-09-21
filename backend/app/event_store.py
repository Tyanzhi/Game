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
            old_metadata = (
                dict(existing.metadata_json)
                if isinstance(existing.metadata_json, dict)
                else {}
            )
            incoming_metadata = dict(event.metadata or {})
            old_origins = set(old_metadata.get("origin_keys") or [])
            incoming_origins = set(incoming_metadata.get("origin_keys") or [])
            combined_origins = sorted(old_origins | incoming_origins)
            new_origin_count = len(incoming_origins - old_origins)

            old_quality_count = max(
                1,
                int(old_metadata.get("independent_source_count", existing.source_count or 1)),
            )
            incoming_quality_count = max(
                1,
                int(incoming_metadata.get("independent_source_count", event.source_count or 1)),
            )
            old_quality = float(old_metadata.get("source_quality_mean", 0.0))
            incoming_quality = float(incoming_metadata.get("source_quality_mean", 0.0))
            quality_mean = (
                old_quality * old_quality_count
                + incoming_quality * incoming_quality_count
            ) / max(1, old_quality_count + incoming_quality_count)

            combined_count = max(
                int(existing.source_count or 1),
                len(combined_origins),
                int(event.source_count or 1),
            )
            existing.source_count = combined_count
            existing.confidence = min(
                0.99,
                max(float(existing.confidence), float(event.confidence))
                + 0.05 * new_origin_count,
            )
            existing.status = (
                "FACT"
                if (combined_count >= 2 and existing.confidence >= 0.60)
                or existing.confidence >= 0.85
                else "CLAIM"
            )

            metadata = old_metadata
            metadata.update(incoming_metadata)
            metadata["origin_keys"] = combined_origins
            metadata["independent_source_count"] = combined_count
            metadata["source_quality_mean"] = quality_mean
            metadata["source_urls"] = sorted(set(
                list(old_metadata.get("source_urls") or [])
                + list(event.source_urls)
            ))
            metadata["actors"] = sorted(set(
                list(old_metadata.get("actors") or [])
                + list(event.actors)
            ))
            old_records = old_metadata.get("source_records")
            incoming_records = incoming_metadata.get("source_records")
            merged_records = []
            seen_records = set()
            for record in (
                (old_records if isinstance(old_records, list) else [])
                + (incoming_records if isinstance(incoming_records, list) else [])
            ):
                if not isinstance(record, dict):
                    continue
                pair = (
                    str(record.get("source_id") or ""),
                    str(record.get("source_url") or ""),
                )
                if pair in seen_records:
                    continue
                seen_records.add(pair)
                merged_records.append(record)
            if merged_records:
                metadata["source_records"] = merged_records
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
