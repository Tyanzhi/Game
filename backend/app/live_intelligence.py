from __future__ import annotations

import asyncio
import os
import re
from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import select

from .db import SessionLocal
from .event_engine import RawEvent, normalize
from .event_store import persist_events
from .models import ActorModel, EventModel, SimulationRunModel
from .simulation import run_simulation
from .runtime_bus import runtime_bus
from .sources.gdelt import fetch_news
from .sources.worldbank import fetch_indicators


DEFAULT_QUERIES = (
    "geopolitics",
    "conflict OR sanctions OR diplomacy",
    "energy OR oil OR gas",
    "economy OR inflation OR trade",
    "protest OR government crisis",
)

_EVENT_RULES = (
    ("natural_disaster", ("earthquake", "flood", "hurricane", "typhoon", "wildfire", "disaster")),
    ("energy_disruption", ("oil", "gas", "pipeline", "energy", "power outage", "blackout")),
    ("economic_crisis", ("recession", "inflation", "sanction", "tariff", "debt crisis", "bank crisis")),
    ("internal_crisis", ("protest", "riot", "coup", "government crisis", "unrest", "strike")),
    ("security_incident", ("attack", "missile", "war", "conflict", "clash", "military", "terror")),
    ("diplomatic_crisis", ("diplomatic", "ambassador", "summit", "ceasefire", "negotiation", "treaty")),
)


def classify_event_type(text: str, fallback: str = "news_report") -> str:
    haystack = text.lower()
    for event_type, keywords in _EVENT_RULES:
        if any(keyword in haystack for keyword in keywords):
            return event_type
    return fallback


def _alias_tokens(actor: ActorModel) -> list[str]:
    raw = {actor.id.lower().strip(), actor.name.lower().strip()}
    aliases = []
    for value in raw:
        if len(value) >= 2:
            aliases.append(value)
        if value == "usa":
            aliases += ["united states", "u.s.", "us government", "washington"]
        elif value == "chn":
            aliases += ["china", "chinese", "beijing"]
        elif value == "rus":
            aliases += ["russia", "russian", "moscow"]
        elif value == "ind":
            aliases += ["india", "indian", "new delhi"]
    return sorted(set(aliases), key=len, reverse=True)


def link_event_actors(event: RawEvent, actors: list[ActorModel]) -> RawEvent:
    text = f"{event.title} {event.description}".lower()
    linked = set(event.actor_ids)
    for actor in actors:
        for alias in _alias_tokens(actor):
            if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text):
                linked.add(actor.id)
                break
    return replace(
        event,
        actor_ids=tuple(sorted(linked)),
        event_type=classify_event_type(text, event.event_type),
    )


async def collect_live_events(
    queries: tuple[str, ...] = DEFAULT_QUERIES,
    max_records_per_query: int = 20,
    include_world_bank: bool = False,
) -> tuple[list[RawEvent], dict]:
    raw: list[RawEvent] = []
    errors: dict[str, str] = {}

    async with SessionLocal() as session:
        actors = (await session.execute(select(ActorModel))).scalars().all()

    for query in queries:
        try:
            rows = await fetch_news(query=query, max_records=max_records_per_query)
            raw.extend(link_event_actors(item, actors) for item in rows)
        except Exception as exc:
            errors[f"gdelt:{query}"] = str(exc)[:500]

    if include_world_bank:
        try:
            indicators = await fetch_indicators()
            raw.extend(link_event_actors(item, actors) for item in indicators)
        except Exception as exc:
            errors["worldbank"] = str(exc)[:500]

    return raw, errors


class LiveIntelligenceState:
    def __init__(self) -> None:
        self.running = False
        self.last_started_at: str | None = None
        self.last_finished_at: str | None = None
        self.last_error: str | None = None
        self.last_simulation_id: str | None = None
        self.last_raw_events = 0
        self.last_normalized_events = 0
        self.last_new_events = 0
        self.last_duplicates = 0
        self.source_errors: dict[str, str] = {}
        self.cycles_completed = 0

    def snapshot(self) -> dict:
        return {
            "running": self.running,
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "last_error": self.last_error,
            "last_simulation_id": self.last_simulation_id,
            "last_raw_events": self.last_raw_events,
            "last_normalized_events": self.last_normalized_events,
            "last_new_events": self.last_new_events,
            "last_duplicates": self.last_duplicates,
            "source_errors": dict(self.source_errors),
            "cycles_completed": self.cycles_completed,
        }


live_state = LiveIntelligenceState()
_live_cycle_lock = asyncio.Lock()
_LIVE_STATE_KEY = "world-engine:live-intelligence-state"


async def persist_live_state() -> None:
    if runtime_bus.enabled:
        await runtime_bus.set_json(_LIVE_STATE_KEY, live_state.snapshot())


async def get_live_state_snapshot() -> dict:
    if runtime_bus.enabled:
        try:
            shared = await runtime_bus.get_json(_LIVE_STATE_KEY)
            if shared is not None:
                return shared
        except Exception:
            pass
    return live_state.snapshot()


async def run_live_intelligence_cycle(
    *,
    broadcast=None,
    queries: tuple[str, ...] = DEFAULT_QUERIES,
    max_records_per_query: int = 20,
    force_simulation: bool = False,
) -> dict:
    if _live_cycle_lock.locked():
        snapshot = live_state.snapshot()
        snapshot["skipped_concurrent"] = True
        return snapshot

    async with _live_cycle_lock:
        live_state.running = True
        live_state.last_started_at = datetime.now(timezone.utc).isoformat()
        live_state.last_error = None
        await persist_live_state()
        simulation_id = None
        try:
            include_world_bank = live_state.cycles_completed % 24 == 0
            raw, source_errors = await collect_live_events(
                queries=queries,
                max_records_per_query=max_records_per_query,
                include_world_bank=include_world_bank,
            )
            normalized = normalize(raw)

            async with SessionLocal() as session:
                new_count, duplicate_count = await persist_events(session, normalized)
                await session.commit()

            if normalized and (new_count > 0 or force_simulation):
                simulation_id = os.getenv("LIVE_SIMULATION_ID", "live-world")
                async with SessionLocal() as session:
                    await run_simulation(
                        session,
                        ticks=1,
                        seed=int(datetime.now(timezone.utc).timestamp()) % 1_000_000,
                        simulation_id=simulation_id,
                        raw_events=raw,
                        broadcast=broadcast,
                        mode="live",
                    )
                    await session.commit()

            if simulation_id is not None:
                live_state.last_simulation_id = simulation_id
            elif live_state.last_simulation_id is None:
                existing_live_id = os.getenv("LIVE_SIMULATION_ID", "live-world")
                async with SessionLocal() as session:
                    existing_run = await session.get(SimulationRunModel, existing_live_id)
                if existing_run is not None:
                    live_state.last_simulation_id = existing_live_id
            live_state.last_raw_events = len(raw)
            live_state.last_normalized_events = len(normalized)
            live_state.last_new_events = new_count
            live_state.last_duplicates = duplicate_count
            live_state.source_errors = source_errors
            live_state.cycles_completed += 1
            return live_state.snapshot()
        except Exception as exc:
            live_state.last_error = str(exc)[:1000]
            raise
        finally:
            live_state.running = False
            live_state.last_finished_at = datetime.now(timezone.utc).isoformat()
            try:
                await persist_live_state()
            except Exception:
                pass


async def live_intelligence_loop(
    *,
    broadcast=None,
    stop_event: asyncio.Event | None = None,
    interval_seconds: int | None = None,
) -> None:
    stop_event = stop_event or asyncio.Event()
    interval = interval_seconds or int(os.getenv("LIVE_INTELLIGENCE_INTERVAL_SECONDS", "300"))
    interval = max(60, interval)

    while not stop_event.is_set():
        try:
            await run_live_intelligence_cycle(broadcast=broadcast)
        except Exception:
            # Status is retained in live_state; one source outage must not kill monitoring.
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def recent_live_events(limit: int = 50) -> list[dict]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(EventModel)
                .order_by(EventModel.event_timestamp.desc(), EventModel.created_at.desc())
                .limit(max(1, min(200, int(limit))))
            )
        ).scalars().all()
        result = []
        for row in rows:
            metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            result.append({
                "id": row.id,
                "event_type": row.event_type,
                "title": row.title,
                "description": row.description,
                "timestamp": row.event_timestamp.isoformat() if row.event_timestamp else None,
                "confidence": float(row.confidence),
                "status": row.status,
                "source_count": row.source_count,
                "independent_source_count": int(
                    metadata.get("independent_source_count", row.source_count)
                ),
                "source_quality_mean": float(
                    metadata.get("source_quality_mean", 0.0)
                ),
                "confidence_model": metadata.get("confidence_model"),
                "actors": metadata.get("actors", []),
                "source_urls": metadata.get("source_urls", []),
            })
        return result
