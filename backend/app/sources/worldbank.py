from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.event_engine import RawEvent

BASE_URL = "https://api.worldbank.org/v2"


async def fetch_indicator(country: str, indicator: str) -> list[RawEvent]:
    url = f"{BASE_URL}/country/{country}/indicator/{indicator}"
    params = {"format": "json", "mrv": 1}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    if len(payload) < 2 or not payload[1]:
        return []

    item = payload[1][0]
    date = item.get("date") or "unknown"
    value = item.get("value")
    return [
        RawEvent(
            source_id="worldbank",
            source_url=str(response.url),
            title=f"World Bank indicator {indicator} for {country}",
            description=f"Observation date={date}; value={value}",
            timestamp=datetime.now(timezone.utc),
            actor_ids=(country.lower(),),
            event_type="economic_indicator",
            confidence=0.98,
        )
    ]
