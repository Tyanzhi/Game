from __future__ import annotations


def normalize_database_url(url: str) -> str:
    value = str(url or "").strip()
    if value.startswith("postgres://"):
        return "postgresql+asyncpg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + value[len("postgresql://"):]
    return value
