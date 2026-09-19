import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.live_outlook import build_live_outlook
from app.models import Base, DecisionModel, ForecastModel, WorldStateVersionModel


@pytest.mark.asyncio
async def test_live_outlook_builds_future_events_and_actor_steps():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        session.add_all([
            WorldStateVersionModel(
                simulation_id="live-1",
                tick=2,
                state_hash="h2",
                parent_hash="h1",
                dataset_version="live",
                state_json={
                    "tick": 2,
                    "actors": {},
                    "metadata": {
                        "crisis_graph": {
                            "nodes": {
                                "c1": {
                                    "event_type": "energy_disruption",
                                    "phase": "escalating",
                                    "intensity": 0.8,
                                    "participants": ["A", "B"],
                                    "escalation": 0.5,
                                    "contagion": 0.7,
                                    "uncertainty": 0.2,
                                }
                            }
                        }
                    },
                },
            ),
            DecisionModel(
                id="d1",
                actor_id="A",
                simulation_id="live-1",
                situation="test",
                selected_action="economic_adjustment",
                confidence=0.75,
                reasoning_factors=[],
                options=[],
                information_state={
                    "target_actor_id": "B",
                    "strategic_posture": "resilience",
                    "crisis_intensity": 0.8,
                },
            ),
            ForecastModel(
                simulation_id="live-1",
                tick=2,
                target="A:stability",
                horizon=5,
                expected=0.62,
                lower=0.45,
                upper=0.75,
                confidence=0.7,
                drivers={},
            ),
        ])
        await session.commit()

        outlook = await build_live_outlook(session, "live-1")
        assert outlook["status"] == "ready"
        assert outlook["future_events"]
        assert any(item["event_type"] == "economic_crisis" for item in outlook["future_events"])
        assert outlook["next_actor_steps"][0]["action"] == "economic_adjustment"
        assert outlook["forecasts"][0]["target"] == "A:stability"

    await engine.dispose()
