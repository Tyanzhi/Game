import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import ActorModel, Base, SimulationRunModel, SimulationTickModel, WorldStateVersionModel
from app.simulation import run_simulation


@pytest.mark.asyncio
async def test_simulation_can_resume_same_timeline():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        session.add_all([
            ActorModel(id="A", name="Alpha"),
            ActorModel(id="B", name="Beta"),
        ])
        await session.commit()

        first = await run_simulation(
            session,
            ticks=1,
            seed=10,
            simulation_id="live-world",
            mode="live",
        )
        second = await run_simulation(
            session,
            ticks=1,
            seed=11,
            simulation_id="live-world",
            mode="live",
        )

        assert first["ticks"] == 1
        assert second["ticks"] == 1

        ticks = (
            await session.execute(
                select(SimulationTickModel)
                .where(SimulationTickModel.simulation_id == "live-world")
                .order_by(SimulationTickModel.tick)
            )
        ).scalars().all()
        assert [row.tick for row in ticks] == [1, 2]

        versions = (
            await session.execute(
                select(WorldStateVersionModel)
                .where(WorldStateVersionModel.simulation_id == "live-world")
                .order_by(WorldStateVersionModel.tick)
            )
        ).scalars().all()
        assert [row.tick for row in versions] == [1, 2]
        assert versions[1].parent_hash == versions[0].state_hash
        assert len(versions[1].state_json["metadata"]["pending_forecasts"]) >= 2

        run = await session.get(SimulationRunModel, "live-world")
        assert run is not None
        assert run.mode == "live"
        assert run.ticks == 2
        assert run.status == "completed"

    await engine.dispose()
