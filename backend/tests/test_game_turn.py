import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.game_turn as game_turn
from app.models import ActorModel, Base, RelationshipModel


@pytest.mark.asyncio
async def test_turn_loop_spends_ap_and_excludes_controlled_actor(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    captured = {}

    async def fake_run_simulation(session, **kwargs):
        captured.update(kwargs)
        return {"simulation_id": kwargs["simulation_id"], "ticks": 1, "history": []}

    async def fake_overview(session, simulation_id):
        return {"simulation_id": simulation_id, "actors": [], "relationships": [], "active_crises": []}

    monkeypatch.setattr(game_turn, "run_simulation", fake_run_simulation)
    monkeypatch.setattr(game_turn, "strategic_overview", fake_overview)

    async with Session() as session:
        session.add_all([
            ActorModel(id="A", name="Alpha"),
            ActorModel(id="B", name="Beta"),
            RelationshipModel(source_actor_id="A", target_actor_id="B"),
        ])
        await session.commit()

        result = await game_turn.play_turn(
            session,
            parent_simulation_id="parent",
            actor_id="A",
            action_type="diplomatic_outreach",
            target_actor_id="B",
            seed=7,
            action_points=2,
        )

        assert result["action_points_spent"] == 1
        assert result["action_points_remaining"] == 1
        assert captured["controlled_actor_id"] == "A"
        assert captured["ticks"] == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_turn_loop_rejects_insufficient_action_points():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        session.add(ActorModel(id="A", name="Alpha"))
        await session.commit()
        with pytest.raises(ValueError):
            await game_turn.play_turn(
                session,
                parent_simulation_id="parent",
                actor_id="A",
                action_type="defensive_posture",
                target_actor_id=None,
                seed=1,
                action_points=1,
            )

    await engine.dispose()
