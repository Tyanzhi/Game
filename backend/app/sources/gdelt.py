from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.event_engine import RawEvent

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _timestamp(value: str | None) -> datetime:
    if value:
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def fetch_news(query: str = "geopolitics", max_records: int = 25) -> list[RawEvent]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max(1, min(max_records, 250)),
        "sort": "datedesc",
    }
    headers = {"User-Agent": "WORLD-ENGINE/0.6 (+https://github.com/Tyanzhi/Game)"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        response = await client.get(GDELT_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    result: list[RawEvent] = []
    for item in payload.get("articles", []):
        url = str(item.get("url", ""))
        title = str(item.get("title", "")).strip()
        domain = str(item.get("domain", ""))
        if not title:
            continue
        result.append(RawEvent(
            source_id=f"gdelt:{domain.lower() or 'unknown'}",
            source_url=url,
            title=title,
            description=title,
            timestamp=_timestamp(item.get("seendate")),
            event_type="news_report",
            confidence=0.55,
            source_quality=0.62 if domain else 0.52,
            raw={
                "domain": domain,
                "provider": "gdelt",
                "source_type": "news_aggregation",
                "language": item.get("language"),
                "sourcecountry": item.get("sourcecountry"),
            },
        ))
    return result
