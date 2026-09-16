from __future__ import annotations

import asyncio

from sqlalchemy import select

from .db import engine, SessionLocal
from .models import ActorModel, Base

SEED_ACTORS = [
    ("usa", "United States"),
    ("chn", "China"),
    ("rus", "Russia"),
]


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        existing = {row.id for row in (await session.execute(select(ActorModel))).scalars()}
        for actor_id, name in SEED_ACTORS:
            if actor_id not in existing:
                session.add(ActorModel(id=actor_id, name=name))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(init_db())
