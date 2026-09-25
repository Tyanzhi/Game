from copy import deepcopy

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.integration_state import load_world_state, persist_tick
from app.models import ActorModel, Base, RelationshipModel, SimulationTickModel, WorldStateVersionModel


@pytest.mark.asyncio
async def test_resume_uses_snapshot_not_current_canonical_rows():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        saved = {
            "tick": 17,
            "actors": {"A": {"id": "A", "stability": 0.25}},
            "metadata": {
                "relationships": {"A:B": {"diplomatic": -0.7}},
                "pending_delayed_effects": [{"due_tick": 19}],
                "beliefs": {"A:B": {"threat": 0.8}},
            },
        }
        original = deepcopy(saved)
        async with sessions() as session:
            session.add_all([
                ActorModel(id="A", name="Alpha", stability=0.95),
                ActorModel(id="B", name="Beta"),
                RelationshipModel(source_actor_id="A", target_actor_id="B", diplomatic=0.9),
                WorldStateVersionModel(simulation_id="branch", tick=17, state_hash="saved", state_json=saved),
            ])
            await session.commit()
            state = await load_world_state(session, "branch")
            assert state.snapshot() == original
            state.actors["A"].values["stability"] = 0.5
            state.metadata["beliefs"]["A:B"]["threat"] = 0.1
            assert saved == original
            assert (await session.get(ActorModel, "A")).stability == 0.95
            await persist_tick(session, "branch", state, {}, [], {}, seed=59)
            await session.commit()
        async with sessions() as session:
            from sqlalchemy import select
            tick = (await session.execute(select(SimulationTickModel))).scalar_one()
            assert tick.seed == 59
            restored = await load_world_state(session, "branch")
            assert restored.snapshot() == original
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_empty_snapshot_does_not_gain_canonical_actors():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add_all([
                ActorModel(id="A", name="Alpha"),
                WorldStateVersionModel(simulation_id="empty", tick=3, state_hash="empty", state_json={
                    "tick": 3, "actors": {}, "metadata": {"relationships": {}},
                }),
            ])
            await session.commit()
            state = await load_world_state(session, "empty")
            assert state.actors == {}
            assert state.metadata["relationships"] == {}
    finally:
        await engine.dispose()
