from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.event_engine import RawEvent

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


async def fetch_news(query: str = "geopolitics", max_records: int = 25) -> list[RawEvent]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": max_records,
        "sort": "datedesc",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(GDELT_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    result: list[RawEvent] = []
    for item in payload.get("articles", []):
        url = item.get("url", "")
        title = item.get("title", "")
        seen = item.get("seendate")
        try:
            timestamp = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc) if seen else datetime.now(timezone.utc)
        except ValueError:
            timestamp = datetime.now(timezone.utc)
        result.append(
            RawEvent(
                source_id="gdelt",
                source_url=url,
                title=title,
                description=item.get("domain", ""),
                timestamp=timestamp,
                event_type="news_report",
                confidence=0.55,
            )
        )
    return result
