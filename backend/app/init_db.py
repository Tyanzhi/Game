from __future__ import annotations
import asyncio
from sqlalchemy import select
from .db import engine, SessionLocal
from .models import ActorModel, Base, CountryModel, RelationshipModel

SEED_ACTORS = [
    ("usa", "United States", 0.78, 0.92, 0.88, 0.90, 0.32, 0.55, 0.62, 0.58, 0.82),
    ("chn", "China", 0.76, 0.90, 0.82, 0.88, 0.28, 0.48, 0.78, 0.58, 0.78),
    ("rus", "Russia", 0.62, 0.72, 0.68, 0.82, 0.42, 0.62, 0.66, 0.50, 0.66),
]
SEED_COUNTRIES = [
    ("USA", "United States", "usa", "North America"),
    ("CHN", "China", "chn", "East Asia"),
    ("RUS", "Russia", "rus", "Eurasia"),
]
SEED_RELATIONSHIPS = [
    ("usa", "chn", -0.25, 0.45, -0.10, 0.35, 0.10, 0.20, -0.15, -0.10),
    ("chn", "usa", -0.25, 0.45, -0.10, 0.35, 0.10, 0.20, -0.15, -0.10),
    ("usa", "rus", -0.45, 0.05, -0.40, 0.00, 0.05, 0.00, -0.30, -0.30),
    ("rus", "usa", -0.45, 0.05, -0.40, 0.00, 0.05, 0.00, -0.30, -0.30),
    ("chn", "rus", 0.35, 0.50, 0.15, 0.45, 0.35, 0.20, 0.20, 0.10),
    ("rus", "chn", 0.35, 0.50, 0.15, 0.45, 0.35, 0.20, 0.20, 0.10),
]

async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        actors = {row.id: row for row in (await session.execute(select(ActorModel))).scalars().all()}
        for row in SEED_ACTORS:
            actor_id, name, stability, economic, diplomatic, security, pressure, risk, patience, threshold, info = row
            if actor_id not in actors:
                session.add(ActorModel(id=actor_id, name=name, stability=stability, economic_capacity=economic, diplomatic_capacity=diplomatic, security_capacity=security, domestic_pressure=pressure, risk_tolerance=risk, strategic_patience=patience, escalation_threshold=threshold, information_quality=info))
        await session.flush()
        countries = {row.id for row in (await session.execute(select(CountryModel))).scalars().all()}
        for country_id, name, actor_id, region in SEED_COUNTRIES:
            if country_id not in countries:
                session.add(CountryModel(id=country_id, name=name, actor_id=actor_id, region=region))
        relationships = {(row.source_actor_id, row.target_actor_id) for row in (await session.execute(select(RelationshipModel))).scalars().all()}
        for row in SEED_RELATIONSHIPS:
            if (row[0], row[1]) not in relationships:
                session.add(RelationshipModel(source_actor_id=row[0], target_actor_id=row[1], diplomatic=row[2], economic=row[3], military=row[4], trade=row[5], energy=row[6], technology=row[7], political=row[8], information=row[9]))
        await session.commit()

if __name__ == "__main__":
    asyncio.run(init_db())
