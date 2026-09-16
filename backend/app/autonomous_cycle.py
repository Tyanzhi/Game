from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .db import SessionLocal
from .event_engine import normalize
from .event_store import apply_events, create_run, create_snapshot, finish_run, persist_events
from .sources.gdelt import fetch_news


async def run_cycle(query: str = "geopolitics", max_records: int = 25) -> dict:
    run_id = f"live-{uuid4().hex}"
    started = datetime.now(timezone.utc)
    raw = await fetch_news(query=query, max_records=max_records)
    normalized = normalize(raw)

    async with SessionLocal() as session:
        run = await create_run(session, run_id, query)
        new_count, duplicate_count = await persist_events(session, normalized)
        changes = await apply_events(session, normalized)
        await create_snapshot(session, run_id, 1, changes)
        await finish_run(session, run, len(raw), new_count, duplicate_count)
        await session.commit()

    return {
        "simulation_id": run_id,
        "status": "completed",
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "raw_events": len(raw),
        "normalized_events": len(normalized),
        "new_events": new_count,
        "duplicates": duplicate_count,
        "state_changes": changes,
        "events": [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp.isoformat(),
                "actors": list(e.actors),
                "event_type": e.event_type,
                "description": e.description,
                "source_ids": list(e.source_ids),
                "source_count": e.source_count,
                "confidence": e.confidence,
                "status": e.status,
                "source_urls": list(e.source_urls),
            }
            for e in normalized
        ],
    }
