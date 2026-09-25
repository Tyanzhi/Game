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
            second = ticks[1].phase_log["explanation"]
            assert second["forecasts"][0]["comparison"]
            assert second["forecasts"][0]["sensitivity"]
            for forecast in second["forecasts"]:
                for comparison in forecast["comparison"]:
                    explained = sum(a["probability_deltas"][comparison["outcome"]] for a in forecast["change_attribution"])
                    assert explained == pytest.approx(comparison["delta"], abs=1e-12)
            assert second["causal_chains"]
            assert second["unexplained_changes"] == []
            effect_ids = {e["effect_id"] for e in second["cascade_effects"]}
            for effect in second["cascade_effects"]:
                assert effect["action_id"] or effect["event_id"]
                if effect["parent_effect_id"]:
                    assert effect["parent_effect_id"] in effect_ids
            # Restart/resume must compare the persisted preceding forecast.
            await run_simulation(session, ticks=1, seed=41, simulation_id="explain-test")
            resumed = (await session.execute(select(SimulationTickModel).where(SimulationTickModel.tick == 3))).scalar_one()
            assert resumed.phase_log["explanation"]["forecasts"][0]["previous_tick"] == 2
    finally:
        await engine.dispose()


def test_cascade_preserves_independent_origins_and_parent_links():
    from app.cascade_engine import CascadeEngine, Effect
    roots = [Effect("A", "B", "stability", -0.1, action_id="first"),
             Effect("A", "B", "stability", -0.2, action_id="second")]
    effects, truncated = CascadeEngine(max_depth=1).run(roots, {"B": ["C"]})
    assert not truncated
    assert len(effects) == 4
    by_id = {e.effect_id: e for e in effects}
    for effect in effects[2:]:
        assert by_id[effect.parent_effect_id].action_id == effect.action_id


def test_counterfactual_is_isolated_and_probabilities_are_computed():
    from app.scenario_engine import ScenarioEngine
    baseline = {"tick": 3, "actors": {"A": {"stability": 0.7}}, "metadata": {}}
    original = deepcopy(baseline)
    result = ScenarioEngine().run(baseline, [{"actor_id": "A", "field": "stability", "delta": -0.2}], 2, "case", 7)
    assert baseline == original
    assert result.baseline_history[0]["state"]["actors"]["A"]["stability"] == 0.7
    assert result.history[0]["state"]["actors"]["A"]["stability"] == pytest.approx(0.5)
    assert result.comparisons[0]["forecasts"][0]["delta"] < 0
    assert result.history[0]["explanation"]["alternative_scenarios"]
    assert result.history[0]["explanation"]["unexplained_changes"] == []
    assert result == ScenarioEngine().run(baseline, [{"actor_id": "A", "field": "stability", "delta": -0.2}], 2, "case", 7)
    with pytest.raises(ValueError):
        ScenarioEngine().run(baseline, [{"actor_id": "A", "field": "stability", "delta": float("nan")}])


@pytest.mark.asyncio
async def test_player_turn_explains_player_and_reaction_and_continues_tick():
    from app.game_turn import play_turn
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add_all([ActorModel(id="A", name="Alpha"), ActorModel(id="B", name="Beta")])
            await session.commit()
            await run_simulation(session, ticks=2, seed=7, simulation_id="parent")
            result = await play_turn(session, parent_simulation_id="parent", actor_id="A",
                action_type="diplomatic_outreach", target_actor_id="B", seed=7)
            saved = (await session.execute(select(SimulationTickModel).where(
                SimulationTickModel.simulation_id == result["simulation_id"]))).scalar_one()
            report = saved.phase_log["explanation"]
            assert saved.tick == 3
            assert any(d.get("control_source") == "player" for d in report["actor_decisions"])
            assert any(d.get("reaction") and d.get("options") for d in report["actor_decisions"])
            assert any(e.get("action_id") == result["player_action"]["action_id"] for e in report["cascade_effects"])
            assert report["unexplained_changes"] == []
    finally:
        await engine.dispose()
