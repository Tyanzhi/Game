from copy import deepcopy
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.event_engine import NormalizedEvent
from app.explainability import build_explanation
from app.models import ActorModel, Base, SimulationTickModel, WorldStateVersionModel
from app.simulation import run_simulation


def test_explanation_is_deterministic_preserves_claims_and_does_not_invent_causes():
    before = {"tick": 0, "actors": {"A": {"stability": 0.7}}, "metadata": {}}
    after = {"tick": 1, "actors": {"A": {"stability": 0.6}}, "metadata": {}}
    original = deepcopy(before)
    args = dict(simulation_id="test", tick=1, seed=42, before=before, after=after,
                events=[NormalizedEvent("e1", datetime(2026, 1, 1, tzinfo=timezone.utc),
                    ("A",), "news_report", "Неподтверждённое сообщение", ("source",), 1, 0.4,
                    "CLAIM", ("https://example.org/e1",))], decisions=[], actions=[], effects=[], forecasts=[])
    report = build_explanation(**args)
    assert report == build_explanation(**args)
    assert before == original
    assert report["observed_data"][0]["status"] == "CLAIM"
    assert report["changes"][0]["delta"] == pytest.approx(-0.1)
    assert report["why_it_happened"] == []
    assert report["alternative_scenarios"] == []
    assert report["limitations"]["complete_causal_provenance"] is False
    assert report["before_hash"] != report["after_hash"]


@pytest.mark.asyncio
async def test_each_tick_persists_report_with_matching_state_hash_and_seed():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add_all([ActorModel(id="A", name="Alpha"), ActorModel(id="B", name="Beta")])
            await session.commit()
            await run_simulation(session, ticks=2, seed=41, simulation_id="explain-test")
        async with sessions() as session:
            ticks = (await session.execute(select(SimulationTickModel).order_by(SimulationTickModel.tick))).scalars().all()
            versions = (await session.execute(select(WorldStateVersionModel).order_by(WorldStateVersionModel.tick))).scalars().all()
            assert len(ticks) == len(versions) == 2
            for tick, version in zip(ticks, versions):
                report = tick.phase_log["explanation"]
                assert report["after_hash"] == version.state_hash
                assert report["seed"] == tick.seed == 41 + tick.tick
                assert report["actor_decisions"]
                assert report["actor_decisions"][0]["options"]
                assert report["forecasts"]
                assert report["observed_data"] == []
            assert ticks[1].phase_log["explanation"]["before_hash"] == versions[0].state_hash
    finally:
        await engine.dispose()
