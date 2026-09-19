"""Validated ingestion pipeline: external data is untrusted until normalized."""
from .event_engine import normalize
from .event_store import persist_events
from .sources.gdelt import fetch_news
from .sources.worldbank import fetch_indicators


async def sync_sources(session, query='geopolitics', max_records=25):
    source_errors = {}
    raw = []

    try:
        raw.extend(await fetch_news(query=query, max_records=max_records))
    except Exception as exc:
        source_errors['gdelt'] = str(exc)[:1000]

    try:
        raw.extend(await fetch_indicators())
    except Exception as exc:
        source_errors['worldbank'] = str(exc)[:1000]

    normalized = normalize(raw)
    new, duplicate = await persist_events(session, normalized)
    await session.commit()
    return {
        'fetched': len(raw),
        'normalized': len(normalized),
        'new': new,
        'duplicates': duplicate,
        'sources': {
            'gdelt': sum(1 for item in raw if item.source_id == 'gdelt'),
            'worldbank': sum(1 for item in raw if item.source_id == 'worldbank'),
        },
        'source_errors': source_errors,
    }
