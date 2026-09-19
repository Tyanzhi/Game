from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field
from sqlalchemy import select
from .models import ActorModel, RelationshipModel, SimulationTickModel, WorldStateVersionModel

TRACKED_FIELDS = (
    'stability', 'economic_capacity', 'diplomatic_capacity', 'security_capacity',
    'domestic_pressure', 'risk_tolerance', 'strategic_patience',
    'escalation_threshold', 'information_quality', 'energy_security',
    'trade_resilience', 'technological_capacity'
)

@dataclass
class ActorState:
    id: str
    values: dict = field(default_factory=dict)

    def snapshot(self):
        return {'id': self.id, **self.values}

    def apply_delta(self, field, delta):
        self.values[field] = float(self.values.get(field, 0.0)) + float(delta)

@dataclass
class WorldState:
    tick: int = 0
    actors: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=lambda: {'relationships': {}, 'markets': {'global_trade': 0.0, 'energy_price': 0.0, 'financial_stress': 0.0, 'commodity_supply': 0.0}})

    def apply_delta(self, actor_id, field, delta):
        if actor_id in self.actors:
            self.actors[actor_id].apply_delta(field, delta)

    def apply_relationship_delta(self, source_actor_id, target_actor_id, field, delta):
        key = f"{source_actor_id}:{target_actor_id}"
        relationship = self.metadata.setdefault("relationships", {}).setdefault(key, {})
        relationship[field] = float(relationship.get(field, 0.0)) + float(delta)

    def snapshot(self):
        return {
            'tick': self.tick,
            'actors': {key: value.snapshot() for key, value in self.actors.items()},
            'metadata': deepcopy(self.metadata),
        }

async def load_world_state(session, simulation_id, tick=0, seed=0):
    state = WorldState(tick=tick)
    latest_version = (
        await session.execute(
            select(WorldStateVersionModel)
            .where(WorldStateVersionModel.simulation_id == simulation_id)
            .order_by(WorldStateVersionModel.tick.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_version is not None:
        saved = latest_version.state_json or {}
        state.tick = int(saved.get("tick", latest_version.tick))
        saved_metadata = saved.get("metadata")
        if isinstance(saved_metadata, dict):
            state.metadata = deepcopy(saved_metadata)

    actors = (await session.execute(select(ActorModel).order_by(ActorModel.id))).scalars().all()
    for actor in actors:
        state.actors[actor.id] = ActorState(
            actor.id,
            {field: float(getattr(actor, field, 0.0) or 0.0) for field in TRACKED_FIELDS},
        )
    relationships = (await session.execute(select(RelationshipModel))).scalars().all()
    state.metadata.setdefault('markets', {
        'global_trade': 0.0,
        'energy_price': 0.0,
        'financial_stress': 0.0,
        'commodity_supply': 0.0,
    })
    db_relationships = {
        f'{rel.source_actor_id}:{rel.target_actor_id}': {
            'diplomatic': float(rel.diplomatic or 0.0),
            'economic': float(rel.economic or 0.0),
            'military': float(rel.military or 0.0),
        }
        for rel in relationships
    }
    saved_relationships = state.metadata.setdefault('relationships', {})
    for key, values in db_relationships.items():
        saved_relationships.setdefault(key, {}).update(values)
    return state

async def sync_world_state_to_db(session, state):
    for actor_id, actor_state in state.actors.items():
        row = await session.get(ActorModel, actor_id)
        if row is None:
            continue
        for field, value in actor_state.values.items():
            if hasattr(row, field):
                setattr(row, field, max(0.0, min(1.0, float(value))))

    relationships = (await session.execute(select(RelationshipModel))).scalars().all()
    for rel in relationships:
        key = f"{rel.source_actor_id}:{rel.target_actor_id}"
        values = state.metadata.get("relationships", {}).get(key, {})
        for field in ("diplomatic", "economic", "military"):
            if field in values:
                setattr(rel, field, max(-1.0, min(1.0, float(values[field]))))

async def persist_tick(session, simulation_id, state, changes, event_ids, phase):
    session.add(SimulationTickModel(
        simulation_id=simulation_id,
        tick=state.tick,
        event_ids=event_ids or [],
        state_changes=changes or {},
        phase_log=phase or {},
    ))
    await session.flush()
