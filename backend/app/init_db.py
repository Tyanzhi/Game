from __future__ import annotations

import asyncio

from sqlalchemy import select

from .db import engine, SessionLocal
from .models import ActorModel, Base
from .world_models import CountryModel, RelationshipModel

SEED_ACTORS = [
    ("usa", "United States"),
    ("chn", "China"),
    ("rus", "Russia"),
]

SEED_COUNTRIES = [
    ("USA", "United States", "usa", "North America"),
    ("CHN", "China", "chn", "East Asia"),
    ("RUS", "Russia", "rus", "Eurasia"),
]


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        existing = {row.id for row in (await session.execute(select(ActorModel))).scalars()}
        for actor_id, name in SEED_ACTORS:
            if actor_id not in existing:
                session.add(ActorModel(id=actor_id, name=name))

        existing_countries = {row.id for row in (await session.execute(select(CountryModel))).scalars()}
        for country_id, name, actor_id, region in SEED_COUNTRIES:
            if country_id not in existing_countries:
                session.add(CountryModel(id=country_id, name=name, actor_id=actor_id, region=region))

        await session.commit()


if __name__ == "__main__":
    asyncio.run(init_db())
