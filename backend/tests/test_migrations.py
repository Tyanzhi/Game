"""Exercise the actual migration path, not metadata.create_all()."""
import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import ActorModel, Base, WorldStateVersionModel
from app.realtime_pipeline import state_hash
from app.simulation import run_simulation


@pytest.mark.parametrize("starting_revision", ["base", "0002_actor_decision_engine"])
def test_migrations_and_persisted_simulation(tmp_path, monkeypatch, starting_revision):
    url = os.getenv("MIGRATION_TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path / 'world.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))

    async def seed_existing_actor():
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("INSERT INTO actors (id, name, created_at, updated_at) "
                                        "VALUES ('usa', 'USA', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
        finally:
            await engine.dispose()

    async def exercise():
        engine = create_async_engine(url)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                for table in Base.metadata.sorted_tables:
                    await session.execute(select(table))
                if starting_revision == "base":
                    session.add(ActorModel(id="usa", name="USA"))
                else:
                    assert (await session.get(ActorModel, "usa")).name == "USA"
                session.add(ActorModel(id="chn", name="China"))
                await session.commit()
                result = await run_simulation(session, ticks=3, seed=42)
                rows = (await session.execute(select(WorldStateVersionModel).order_by(WorldStateVersionModel.tick))).scalars().all()
                assert len(rows) == 3
                for snapshot, row in zip(result["history"], rows):
                    assert snapshot == row.state_json
                    assert state_hash(snapshot) == row.state_hash
                assert rows[1].parent_hash == rows[0].state_hash
                assert rows[2].parent_hash == rows[1].state_hash
        finally:
            await engine.dispose()

    async def assert_empty():
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                tables = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
                assert set(tables) <= {"alembic_version"}
        finally:
            await engine.dispose()

    command.upgrade(config, starting_revision)
    if starting_revision != "base":
        asyncio.run(seed_existing_actor())
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # Repeated deployment must be harmless.
    try:
        asyncio.run(exercise())
    finally:
        command.downgrade(config, "base")
    asyncio.run(assert_empty())
