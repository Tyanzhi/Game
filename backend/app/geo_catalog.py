from __future__ import annotations

import hashlib

GEO_CATALOG = {
    "usa": (38.0, -97.0, "North America"),
    "us": (38.0, -97.0, "North America"),
    "united states": (38.0, -97.0, "North America"),
    "chn": (35.0, 103.0, "East Asia"),
    "china": (35.0, 103.0, "East Asia"),
    "rus": (61.0, 105.0, "Eurasia"),
    "russia": (61.0, 105.0, "Eurasia"),
    "ind": (21.0, 78.0, "South Asia"),
    "india": (21.0, 78.0, "South Asia"),
    "jpn": (36.0, 138.0, "East Asia"),
    "japan": (36.0, 138.0, "East Asia"),
    "gbr": (55.0, -3.0, "Europe"),
    "uk": (55.0, -3.0, "Europe"),
    "united kingdom": (55.0, -3.0, "Europe"),
    "fra": (46.0, 2.0, "Europe"),
    "france": (46.0, 2.0, "Europe"),
    "deu": (51.0, 10.0, "Europe"),
    "germany": (51.0, 10.0, "Europe"),
    "bra": (-10.0, -55.0, "South America"),
    "brazil": (-10.0, -55.0, "South America"),
    "zaf": (-30.0, 25.0, "Southern Africa"),
    "south africa": (-30.0, 25.0, "Southern Africa"),
    "sau": (24.0, 45.0, "Middle East"),
    "saudi arabia": (24.0, 45.0, "Middle East"),
    "irn": (32.0, 53.0, "Middle East"),
    "iran": (32.0, 53.0, "Middle East"),
    "tur": (39.0, 35.0, "Eurasia"),
    "turkey": (39.0, 35.0, "Eurasia"),
    "kor": (36.0, 128.0, "East Asia"),
    "south korea": (36.0, 128.0, "East Asia"),
    "aus": (-25.0, 133.0, "Oceania"),
    "australia": (-25.0, 133.0, "Oceania"),
    "idn": (-2.0, 118.0, "Southeast Asia"),
    "indonesia": (-2.0, 118.0, "Southeast Asia"),
    "mex": (23.0, -102.0, "North America"),
    "mexico": (23.0, -102.0, "North America"),
    "can": (56.0, -106.0, "North America"),
    "canada": (56.0, -106.0, "North America"),
    "eu": (50.0, 10.0, "Europe"),
    "european union": (50.0, 10.0, "Europe"),
}


def _fallback_coordinates(key: str) -> tuple[float, float]:
    digest = hashlib.sha256(key.encode()).digest()
    lat_unit = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    lon_unit = int.from_bytes(digest[4:8], "big") / 0xFFFFFFFF
    return (-55.0 + lat_unit * 125.0, -170.0 + lon_unit * 340.0)


def actor_geography(actor_id: str, name: str = "", region: str = "") -> dict:
    candidates = [actor_id.lower().strip(), name.lower().strip()]
    for key in candidates:
        if key in GEO_CATALOG:
            lat, lon, catalog_region = GEO_CATALOG[key]
            return {
                "latitude": lat,
                "longitude": lon,
                "region": region or catalog_region,
                "source": "catalog",
            }
    lat, lon = _fallback_coordinates(actor_id or name or "unknown")
    return {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "region": region or "Unassigned",
        "source": "deterministic_fallback",
    }
