from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .event_engine import NormalizedEvent
from .models import ActorModel, EventModel, EventSourceModel, SimulationRunModel, SimulationTickModel, WorldSnapshotModel


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


async def persist_events(session: AsyncSession, events: list[NormalizedEvent]) -> tuple[int, int]:
    new_count = 0
    duplicate_count = 0
    for event in events:
        existing = await session.get(EventModel, event.event_id)
        if existing:
            duplicate_count += 1
            continue
        row = EventModel(
            id=event.event_id,
            event_type=event.event_type,
            title=event.description[:500],
            description=event.description,
            event_timestamp=event.timestamp,
            confidence=event.confidence,
            status=event.status,
            source_count=event.source_count,
        )
        session.add(row)
        for source_id in event.source_ids:
            session.add(EventSourceModel(
                event_id=event.event_id,
                source_id=source_id,
                source_url="",
                source_title=event.description[:500],
            ))
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
            changes[actor_id] = {
                "stability": actor.stability,
                "domestic_pressure": actor.domestic_pressure,
            }
    return changes


async def create_snapshot(session: AsyncSession, simulation_id: str, tick: int, changes: dict) -> None:
    session.add(WorldSnapshotModel(
        tick=tick,
        simulation_id=simulation_id,
        model_version="world-state-v1",
        dataset_version="live",
        random_seed=0,
        state_json={"actor_changes": changes},
    ))
    session.add(SimulationTickModel(
        simulation_id=simulation_id,
        tick=tick,
        event_ids=list(changes.keys()),
        state_changes=changes,
    ))


async def create_run(session: AsyncSession, run_id: str, query: str) -> SimulationRunModel:
    run = SimulationRunModel(id=run_id, query=query)
    session.add(run)
    await session.flush()
    return run


async def finish_run(session: AsyncSession, run: SimulationRunModel, raw: int, new: int, dedup: int) -> None:
    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    run.events_ingested = raw
    run.events_new = new
    run.events_deduplicated = dedup
