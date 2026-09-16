from __future__ import annotations

from datetime import datetime, timezone

from app.event_engine import normalize
from app.sources.gdelt import fetch_news


async def run_cycle(query: str = "geopolitics", max_records: int = 25) -> dict:
    raw = await fetch_news(query=query, max_records=max_records)
    events = normalize(raw)
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "raw_events": len(raw),
        "normalized_events": len(events),
        "events": [
            {
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "actors": list(event.actors),
                "event_type": event.event_type,
                "description": event.description,
                "source_ids": list(event.source_ids),
                "source_count": event.source_count,
                "confidence": event.confidence,
                "status": event.status,
            }
            for event in events
        ],
    }
