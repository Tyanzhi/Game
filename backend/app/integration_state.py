from __future__ import annotations
from dataclasses import dataclass, field
from sqlalchemy import select
from .models import ActorModel, SimulationTickModel

@dataclass
class ActorState:
    id: str
    values: dict = field(default_factory=dict)
    def snapshot(self): return {'id': self.id, **self.values}
    def apply_delta(self, field, delta): self.values[field] = float(self.values.get(field, 0)) + float(delta)
@dataclass
class WorldState:
    tick: int = 0
    actors: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=lambda: {'relationships': {}})
    def apply_delta(self, actor_id, field, delta):
        if actor_id in self.actors: self.actors[actor_id].apply_delta(field, delta)
    def snapshot(self): return {'tick': self.tick, 'actors': {k: v.snapshot() for k,v in self.actors.items()}, 'metadata': self.metadata}

async def load_world_state(session, simulation_id, tick=0, seed=0):
    rows=(await session.execute(select(ActorModel))).scalars().all(); state=WorldState(tick=tick)
    for a in rows:
        state.actors[a.id]=ActorState(a.id, {k:getattr(a,k) for k in ('stability','economic_capacity','diplomatic_capacity','security_capacity','domestic_pressure','risk_tolerance','strategic_patience','escalation_threshold','information_quality','energy_security','trade_resilience','technological_capacity')})
    return state
async def sync_world_state_to_db(session,state):
    for aid,a in state.actors.items():
        row=await session.get(ActorModel,aid)
        if row:
            for k,v in a.values.items():
                if hasattr(row,k): setattr(row,k,max(0,min(1,float(v))))
async def persist_tick(session,state,changes,event_ids,phase):
    session.add(SimulationTickModel(simulation_id='current',tick=state.tick,event_ids=event_ids,state_changes=changes,phase_log=phase))
    await session.flush()
