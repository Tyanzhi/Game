import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import ActorModel, Base, EffectModel, WorldStateVersionModel
from app.prediction_center import build_prediction_center


@pytest.mark.asyncio
async def test_prediction_center_builds_horizons_scenarios_graph_and_calibration():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        session.add_all([
            ActorModel(
                id="A",
                name="Alpha",
                stability=0.72,
                economic_capacity=0.70,
                security_capacity=0.68,
                domestic_pressure=0.25,
                energy_security=0.66,
                trade_resilience=0.71,
            ),
            ActorModel(
                id="B",
                name="Beta",
                stability=0.61,
                economic_capacity=0.62,
                security_capacity=0.74,
                domestic_pressure=0.36,
                energy_security=0.58,
                trade_resilience=0.60,
            ),
            WorldStateVersionModel(
                simulation_id="sim-prediction",
                tick=1,
                state_hash="h1",
                parent_hash=None,
                dataset_version="live",
                state_json={
                    "tick": 1,
                    "actors": {},
                    "metadata": {
                        "markets": {
                            "financial_stress": 0.10,
                            "energy_price": 0.05,
                        },
                        "crisis_graph": {"nodes": {}},
                    },
                },
            ),
            WorldStateVersionModel(
                simulation_id="sim-prediction",
                tick=2,
                state_hash="h2",
                parent_hash="h1",
                dataset_version="live",
                state_json={
                    "tick": 2,
                    "actors": {},
                    "metadata": {
                        "markets": {
                            "financial_stress": 0.26,
                            "energy_price": 0.18,
                        },
                        "forecast_calibration": {
                            "A:stability": {
                                "count": 4,
                                "brier_sum": 0.40,
                                "mean_brier": 0.10,
                            }
                        },
                        "crisis_graph": {
                            "nodes": {
                                "c1": {
                                    "event_type": "economic_crisis",
                                    "phase": "escalating",
                                    "intensity": 0.76,
                                    "participants": ["A", "B"],
                                    "contagion": 0.70,
                                    "escalation": 0.55,
                                    "uncertainty": 0.20,
                                }
                            }
                        },
                    },
                },
            ),
            EffectModel(
                simulation_id="sim-prediction",
                tick=2,
                source="A",
                target="B",
                field="diplomatic",
                delta=-0.04,
                confidence=0.8,
                depth=0,
                mechanism="strategic_pressure",
            ),
        ])
        await session.commit()

        result = await build_prediction_center(session, "sim-prediction")

        assert result["horizons"] == [1, 7, 30]
        assert result["model_version"] == "prediction-center-v1"
        assert len(result["actors"]) == 2
        assert set(result["actors"][0]["horizons"]) == {"1", "7", "30"}
        assert result["calibration"]["scored_targets"] == 1
        assert result["calibration"]["mean_brier"] == pytest.approx(0.10)
        assert result["change_since_previous_snapshot"]["market_stress_delta"] > 0

        actor_scenarios = result["scenario_matrix"][0]["scenarios"]
        baseline = actor_scenarios["baseline"]["7"]["expected"]
        escalation = actor_scenarios["escalation"]["7"]["expected"]
        stabilization = actor_scenarios["stabilization"]["7"]["expected"]
        assert escalation < stabilization
        assert baseline != escalation

        node_kinds = {node["kind"] for node in result["causal_graph"]["nodes"]}
        assert "crisis" in node_kinds
        assert "actor" in node_kinds
        assert result["causal_graph"]["edges"]


@pytest.mark.asyncio
async def test_prediction_center_requires_world_state():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        with pytest.raises(ValueError):
            await build_prediction_center(session, "missing")

    await engine.dispose()
