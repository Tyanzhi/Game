import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import ActorModel, Base, WorldStateVersionModel
from app.operations_center import build_operations_center, set_alert_state


@pytest.mark.asyncio
async def test_operations_center_builds_and_acknowledges_alerts():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        session.add_all([
            ActorModel(
                id="A",
                name="Alpha",
                stability=0.35,
                domestic_pressure=0.72,
                information_quality=0.40,
                economic_capacity=0.65,
                security_capacity=0.70,
                energy_security=0.60,
                trade_resilience=0.64,
            ),
            ActorModel(
                id="B",
                name="Beta",
                stability=0.70,
                domestic_pressure=0.22,
                information_quality=0.75,
            ),
            WorldStateVersionModel(
                simulation_id="sim-ops",
                tick=5,
                state_hash="ops5",
                parent_hash="ops4",
                dataset_version="live",
                state_json={
                    "tick": 5,
                    "actors": {},
                    "metadata": {
                        "markets": {
                            "financial_stress": 0.42,
                            "energy_price": 0.19,
                            "global_trade": -0.18,
                            "commodity_supply": -0.03,
                        },
                        "forecast_calibration": {
                            "A:stability": {
                                "count": 3,
                                "brier_sum": 0.36,
                                "mean_brier": 0.12,
                            }
                        },
                        "crisis_graph": {
                            "nodes": {
                                "c1": {
                                    "event_type": "security_incident",
                                    "phase": "escalating",
                                    "intensity": 0.85,
                                    "escalation": 0.72,
                                    "contagion": 0.61,
                                    "uncertainty": 0.30,
                                    "participants": ["A", "B"],
                                }
                            }
                        },
                    },
                },
            ),
        ])
        await session.commit()

        center = await build_operations_center(session, "sim-ops")
        assert center["tick"] == 5
        assert center["summary"]["total"] >= 4
        assert center["summary"]["critical"] >= 1
        assert center["posture"] == "critical"
        assert "A" in center["brief"]["watch_actors"]
        assert "c1" in center["brief"]["watch_crises"]

        alert = center["alerts"][0]
        assert alert["operator_action"]
        assert center["brief"]["recommended_actions"]
        assert center["brief"]["recommended_actions"][0]["action"]

        result = await set_alert_state(
            session,
            "sim-ops",
            alert["id"],
            status="acknowledged",
            acknowledged_by="operator",
            note="reviewed",
        )
        assert result["status"] == "acknowledged"

        reloaded = await build_operations_center(session, "sim-ops")
        same = next(item for item in reloaded["alerts"] if item["id"] == alert["id"])
        assert same["status"] == "acknowledged"
        assert same["acknowledged_by"] == "operator"
        assert same["note"] == "reviewed"
        assert reloaded["summary"]["acknowledged"] >= 1

        reopened = await set_alert_state(
            session,
            "sim-ops",
            alert["id"],
            status="open",
        )
        assert reopened["status"] == "open"

    await engine.dispose()


@pytest.mark.asyncio
async def test_operations_center_requires_state_and_rejects_unknown_alert():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        with pytest.raises(ValueError):
            await build_operations_center(session, "missing")

        session.add(
            WorldStateVersionModel(
                simulation_id="sim-empty",
                tick=1,
                state_hash="empty1",
                parent_hash=None,
                dataset_version="live",
                state_json={"tick": 1, "actors": {}, "metadata": {}},
            )
        )
        await session.commit()

        with pytest.raises(ValueError):
            await set_alert_state(
                session,
                "sim-empty",
                "missing-alert",
                status="acknowledged",
            )

    await engine.dispose()
