import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models import (
    Base,
    ActorModel,
    DecisionModel,
    ForecastModel,
    RelationshipModel,
    SimulationTickModel,
    WorldStateVersionModel,
)
from app.strategic_overview import strategic_overview


@pytest.mark.asyncio
async def test_strategic_overview_aggregates_latest_state():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        session.add_all([
            ActorModel(id="A", name="Alpha"),
            ActorModel(id="B", name="Beta"),
            RelationshipModel(
                source_actor_id="A", target_actor_id="B",
                diplomatic=0.4, economic=0.6, military=0.1
            ),
            WorldStateVersionModel(
                simulation_id="sim-1",
                tick=3,
                state_hash="hash-3",
                parent_hash="hash-2",
                dataset_version="live",
                state_json={
                    "tick": 3,
                    "actors": {
                        "A": {"id": "A", "stability": 0.81, "economic_capacity": 0.74},
                        "B": {"id": "B", "stability": 0.62, "economic_capacity": 0.68},
                    },
                    "metadata": {
                        "markets": {"energy_price": 0.15, "financial_stress": 0.2},
                        "beliefs": {"A:B": {"threat": 0.3}},
                        "strategic_memory": {"A:B": {"trust": 0.7}},
                        "crisis_graph": {
                            "nodes": {
                                "c1": {
                                    "event_type": "energy_disruption",
                                    "phase": "escalating",
                                    "intensity": 0.7,
                                    "participants": ["A", "B"],
                                    "duration": 2,
                                    "escalation": 0.35,
                                    "contagion": 1.0,
                                    "uncertainty": 0.2,
                                }
                            }
                        },
                        "multilateral_coalitions": [{"members": ["A", "B"], "reliability": 0.72}],
                        "brinkmanship": [{"actors": ["A", "B"], "escalation_risk": 0.4}],
                    },
                },
            ),
            SimulationTickModel(
                simulation_id="sim-1", tick=3, seed=42,
                state_changes={"A": {"stability": 0.01}},
                phase_log={"forecast": {"model_version": "forecast-v2"}},
            ),
            DecisionModel(
                id="d1", actor_id="A", simulation_id="sim-1",
                situation="test", selected_action="diplomatic_outreach",
                confidence=0.8, reasoning_factors=["test"], options=[],
                information_state={},
            ),
            ForecastModel(
                simulation_id="sim-1", tick=3, target="A:stability",
                horizon=5, expected=0.75, lower=0.6, upper=0.85,
                confidence=0.7, drivers={},
            ),
        ])
        await session.commit()

        overview = await strategic_overview(session, "sim-1")

        assert overview["tick"] == 3
        assert overview["state_hash"] == "hash-3"
        assert overview["actors"][0]["stability"] == 0.81
        assert overview["markets"]["energy_price"] == 0.15
        assert overview["active_crises"][0]["event_type"] == "energy_disruption"
        assert overview["decisions"][0]["selected_action"] == "diplomatic_outreach"
        assert overview["forecasts"][0]["target"] == "A:stability"
        assert overview["belief_edges"] == 1
        assert overview["strategic_memory_edges"] == 1

    await engine.dispose()
