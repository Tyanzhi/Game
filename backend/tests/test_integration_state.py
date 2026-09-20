import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.integration_state import (
    RELATIONSHIP_FIELDS,
    load_world_state,
    sync_world_state_to_db,
)
from app.models import ActorModel, Base, RelationshipModel, WorldStateVersionModel


@pytest.mark.asyncio
async def test_relationship_sync_persists_all_dimensions_and_new_edges():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        session.add_all([
            ActorModel(id="A", name="Alpha"),
            ActorModel(id="B", name="Beta"),
            RelationshipModel(
                source_actor_id="A",
                target_actor_id="B",
                diplomatic=0.1,
                economic=0.2,
                military=0.3,
                trade=0.4,
                energy=0.5,
                technology=0.6,
                political=0.7,
                information=0.8,
            ),
        ])
        await session.commit()

        state = await load_world_state(session, "sim-sync")
        loaded = state.metadata["relationships"]["A:B"]
        assert set(RELATIONSHIP_FIELDS).issubset(loaded)
        assert loaded["technology"] == pytest.approx(0.6)
        assert loaded["information"] == pytest.approx(0.8)

        state.metadata["relationships"]["A:B"].update({
            "diplomatic": -0.4,
            "economic": 0.25,
            "military": 0.55,
            "trade": 0.65,
            "energy": -0.2,
            "technology": 0.75,
            "political": -0.35,
            "information": 0.45,
        })
        state.metadata["relationships"]["B:A"] = {
            "diplomatic": 0.15,
            "economic": 0.20,
            "military": -0.10,
            "trade": 0.30,
            "energy": 0.25,
            "technology": 0.35,
            "political": 0.10,
            "information": 0.40,
        }
        await sync_world_state_to_db(session, state)
        await session.commit()

        rows = (
            await session.execute(select(RelationshipModel))
        ).scalars().all()
        by_key = {f"{row.source_actor_id}:{row.target_actor_id}": row for row in rows}
        assert set(by_key) == {"A:B", "B:A"}
        assert by_key["A:B"].energy == pytest.approx(-0.2)
        assert by_key["A:B"].political == pytest.approx(-0.35)
        assert by_key["B:A"].trade == pytest.approx(0.30)
        assert by_key["B:A"].technology == pytest.approx(0.35)

    await engine.dispose()


@pytest.mark.asyncio
async def test_market_metadata_resumes_from_world_version():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        session.add_all([
            ActorModel(id="A", name="Alpha"),
            WorldStateVersionModel(
                simulation_id="live-world",
                tick=9,
                state_hash="market9",
                parent_hash="market8",
                dataset_version="live",
                state_json={
                    "tick": 9,
                    "actors": {},
                    "metadata": {
                        "markets": {
                            "global_trade": -0.21,
                            "energy_price": 0.32,
                            "financial_stress": 0.27,
                            "commodity_supply": -0.14,
                        }
                    },
                },
            ),
        ])
        await session.commit()

        state = await load_world_state(session, "live-world")
        assert state.tick == 9
        assert state.metadata["markets"]["global_trade"] == pytest.approx(-0.21)
        assert state.metadata["markets"]["energy_price"] == pytest.approx(0.32)
        assert state.metadata["markets"]["financial_stress"] == pytest.approx(0.27)
        assert state.metadata["markets"]["commodity_supply"] == pytest.approx(-0.14)

    await engine.dispose()
