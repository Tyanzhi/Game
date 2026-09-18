"""Validated ingestion pipeline: external data is untrusted until normalized."""
from datetime import datetime, timezone
from .event_engine import RawEvent, normalize
from .event_store import persist_events
from .sources.real_sources import fetch_gdelt, fetch_world_bank


def _parse_dt(value):
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def validate_gdelt(rows):
    events = []
    for row in rows or []:
        title = str(row.get('title', '')).strip()
        if not title or not row.get('source_url'):
            continue
        events.append(RawEvent(
            title=title, description=str(row.get('description') or title),
            event_type='news', source_id='gdelt', source_url=row['source_url'],
            confidence=0.55, timestamp=_parse_dt(row.get('timestamp')),
        ))
    return events


def validate_world_bank(rows):
    events = []
    for row in rows or []:
        if row.get('value') is None or not row.get('country') or not row.get('indicator'):
            continue
        title = f"{row['country']} {row['indicator']} {row.get('year', '')}"
        description = f"Indicator {row['indicator']} for {row['country']}: {row['value']} ({row.get('year', '')})"
        events.append(RawEvent(
            title=title, description=description, event_type='economic_indicator',
            source_id='worldbank', confidence=0.98,
            actor_ids=(str(row['country']).lower(),),
            timestamp=_parse_dt(f"{row.get('year', '2000')}-12-31T00:00:00+00:00"),
        ))
    return events


async def sync_sources(session, query='geopolitics', max_records=25):
    gdelt_rows = await fetch_gdelt(query, max_records)
    wb_rows = await fetch_world_bank()
    raw = validate_gdelt(gdelt_rows) + validate_world_bank(wb_rows)
    normalized = normalize(raw)
    new, duplicate = await persist_events(session, normalized)
    await session.commit()
    return {
        'fetched': len(raw), 'normalized': len(normalized),
        'new': new, 'duplicates': duplicate,
        'sources': {'gdelt': len(gdelt_rows), 'worldbank': len(wb_rows)},
    }
