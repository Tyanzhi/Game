from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.event_engine import RawEvent

WORLD_BANK_API = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
INDICATORS = {"NY.GDP.MKTP.KD.ZG": "GDP growth", "FP.CPI.TOTL.ZG": "Inflation"}


async def fetch_indicators(country_codes: tuple[str, ...] = ("USA", "CHN", "RUS")) -> list[RawEvent]:
    events: list[RawEvent] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": "WORLD-ENGINE/1.0"}) as client:
        for country in country_codes:
            for indicator, label in INDICATORS.items():
                response = await client.get(WORLD_BANK_API.format(country=country, indicator=indicator), params={"format": "json", "per_page": 5})
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
                    continue
                latest = next((row for row in payload[1] if row.get("value") is not None), None)
                if not latest:
                    continue
                value = float(latest["value"])
                year = str(latest.get("date", ""))
                events.append(RawEvent(
                    source_id="worldbank",
                    source_url=f"https://data.worldbank.org/indicator/{indicator}",
                    title=f"{country} {label}: {value:.2f}% ({year})",
                    description=f"World Bank indicator {label} for {country}: {value:.2f}% in {year}.",
                    timestamp=datetime(int(year), 12, 31, tzinfo=timezone.utc) if year.isdigit() else datetime.now(timezone.utc),
                    actor_ids=(country.lower(),), event_type="economic_indicator", confidence=0.98,
                    raw={"indicator": indicator, "indicator_name": label, "country": country, "year": year, "value": value},
                ))
    return events
