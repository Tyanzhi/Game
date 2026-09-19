import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import ActorModel, Base, RelationshipModel, SimulationTickModel, WorldStateVersionModel
from app.strategic_gameplay import (
    actor_detail,
    causal_chain,
    crisis_detail,
    scenario_tree_detail,
    submit_player_action,
)


@pytest.mark.asyncio
async def test_gameplay_services_cover_actor_crisis_scenario_action_and_causal_chain():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        session.add_all([
            ActorModel(id="usa", name="USA", stability=0.8),
            ActorModel(id="chn", name="China", stability=0.7),
            RelationshipModel(
                source_actor_id="usa",
                target_actor_id="chn",
                diplomatic=0.1,
                economic=0.6,
                military=0.2,
            ),
            SimulationTickModel(
                simulation_id="sim-game",
                tick=4,
                seed=42,
                state_changes={},
                phase_log={},
            ),
            WorldStateVersionModel(
                simulation_id="sim-game",
                tick=4,
                state_hash="h4",
                parent_hash="h3",
                dataset_version="live",
                state_json={
                    "tick": 4,
                    "actors": {},
                    "metadata": {
                        "markets": {
                            "financial_stress": 0.2,
                            "energy_price": 0.1,
                        },
                        "crisis_graph": {
                            "nodes": {
                                "crisis-1": {
                                    "event_type": "economic_crisis",
                                    "phase": "escalating",
                                    "intensity": 0.65,
                                    "participants": ["usa", "chn"],
                                    "duration": 2,
                                    "escalation": 0.3,
                                    "contagion": 1.0,
                                    "uncertainty": 0.2,
                                }
                            },
                            "edges": [
                                {
                                    "from": "crisis-1",
                                    "to": "chn",
                                    "tick": 4,
                                    "mechanism": "crisis_contagion",
                                    "strength": 0.5,
                                }
                            ],
                            "history": [
                                {
                                    "crisis_id": "crisis-1",
                                    "tick": 4,
                                    "phase": "escalating",
                                    "intensity": 0.65,
                                    "participants": ["usa", "chn"],
                                }
                            ],
                        },
                    },
                },
            ),
        ])
        await session.commit()

        detail = await actor_detail(session, "sim-game", "usa")
        assert detail["actor"]["geography"]["source"] == "catalog"
        assert detail["relationships"][0]["target"] == "chn"

        crisis = await crisis_detail(session, "sim-game", "crisis-1")
        assert crisis["crisis"]["event_type"] == "economic_crisis"
        assert len(crisis["participants"]) == 2

        tree = await scenario_tree_detail(session, "sim-game", "usa", 2, 2)
        assert tree["depth"] == 2
        assert tree["leaf_count"] == 4

        before_pressure = (await session.get(ActorModel, "usa")).domestic_pressure
        action = await submit_player_action(
            session,
            "sim-game",
            actor_id="usa",
            action_type="diplomatic_outreach",
            target_actor_id="chn",
        )
        assert action["status"] == "executed"
        assert action["effects"]["target_actor_id"] == "chn"
        assert (await session.get(ActorModel, "usa")).domestic_pressure < before_pressure

        chain = await causal_chain(session, "sim-game")
        assert chain["effect_count"] >= 1
        assert any(node.get("kind") == "effect" for node in chain["nodes"])

    await engine.dispose()


@pytest.mark.asyncio
async def test_player_action_rejects_invalid_target_and_action():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        session.add(ActorModel(id="A", name="Alpha"))
        await session.commit()

        with pytest.raises(ValueError):
            await submit_player_action(session, "sim", "A", "not_allowed")
        with pytest.raises(ValueError):
            await submit_player_action(
                session,
                "sim",
                "A",
                "diplomatic_outreach",
                target_actor_id="missing",
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_targeted_diplomacy_creates_missing_relationship():
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

        result = await submit_player_action(
            session,
            "sim-new-rel",
            actor_id="A",
            action_type="diplomatic_outreach",
            target_actor_id="B",
        )
        assert result["status"] == "executed"

        rows = (
            await session.execute(
                __import__("sqlalchemy").select(RelationshipModel).where(
                    RelationshipModel.source_actor_id == "A",
                    RelationshipModel.target_actor_id == "B",
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].diplomatic > 0

    await engine.dispose()
