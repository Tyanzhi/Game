from __future__ import annotations
from uuid import uuid4
from datetime import datetime, timezone
from .models import SimulationRunModel, ActorPerceptionModel, EffectModel, ForecastModel
from .integration_state import load_world_state, sync_world_state_to_db, persist_tick
from .event_engine import normalize, RawEvent
from .decision_engine import decide_all
from .action_executor import execute_actions
from .cascade_engine import CascadeEngine, Effect
from .perception_engine import PerceptionEngine
from .forecasting_engine import forecast
from .engines import economic,social,conflict,energy
from .realtime_pipeline import save_world_version
from .simulation_tick import SimulationTickEngine, TickContext

async def run_simulation(session, ticks=5, seed=0, simulation_id=None, raw_events=None, broadcast=None):
    ticks=max(1,min(120,int(ticks))); simulation_id=simulation_id or f'sim-{uuid4().hex}'; run=SimulationRunModel(id=simulation_id,mode='simulation',status='running',query='local'); session.add(run); await session.flush()
    state=await load_world_state(session,simulation_id,0,seed); normalized=normalize(raw_events or []); event_ids=[e.event_id for e in normalized]
    from .event_store import persist_events
    await persist_events(session,normalized)
    history=[]; parent_hash=None
    for tick in range(1,ticks+1):
        state.tick=tick; phase={}; changes={}; tick_context=TickContext(simulation_id,tick,seed+tick)
        pe=PerceptionEngine()
        for aid,a in state.actors.items():
            facts=[{'fact_id':e.event_id,'value':e.description,'confidence':e.confidence,'source_ids':[s.get('source_id','unknown') for s in e.metadata.get('sources',[])]} for e in normalized]
            p=pe.build(aid,facts,a.values.get('information_quality',.7)); session.add(ActorPerceptionModel(simulation_id=simulation_id,tick=tick,actor_id=aid,facts_json={k:v.__dict__ for k,v in p.facts.items()}))
        phase['perception']=len(state.actors); decisions=await decide_all(session,simulation_id); phase['decision']=len(decisions)
        actions=await execute_actions(session,state,[d['action_id'] for d in decisions]); phase['action']=actions
        adjacency={}
        for key in state.metadata.get('relationships',{}):
            a,b=key.split(':',1); adjacency.setdefault(a,[]).append(b)
        base=[]
        for d in actions:
            for aid,vals in d['effects'].items():
                for field,delta in vals.items(): base.append(Effect('action',aid,field,delta,1.0))
        cascaded,truncated=CascadeEngine().run(base,adjacency); phase['cascade']={'count':len(cascaded),'truncated':truncated}
        for e in cascaded:
            if e.depth>0:
                state.apply_delta(e.target,e.field,e.delta); session.add(EffectModel(simulation_id=simulation_id,tick=tick,source=e.source,target=e.target,field=e.field,delta=e.delta,confidence=e.confidence,depth=e.depth,mechanism=e.mechanism))
        state_results={aid:a for aid,a in state.actors.items()}
        for bundle in (economic(state_results),social(state_results),energy(state_results),conflict(state_results)):
            for aid,r in bundle.items():
                for field,delta in r.changes.items(): state.apply_delta(aid,field,delta); changes.setdefault(aid,{})[field]=changes.setdefault(aid,{}).get(field,0)+delta
        phase['engines']=changes
        for aid,a in state.actors.items():
            f=forecast(f'{aid}:stability',a.values.get('stability',.7),{'economic':changes.get(aid,{}).get('economic_capacity',0),'social':changes.get(aid,{}).get('domestic_pressure',0)*-.5},5,seed)
            session.add(ForecastModel(simulation_id=simulation_id,tick=tick,target=f.target,horizon=f.horizon,expected=f.expected,lower=f.lower,upper=f.upper,confidence=f.confidence,drivers=f.drivers))
        await sync_world_state_to_db(session,state); await persist_tick(session,state,changes,event_ids,phase); snapshot=state.snapshot()
        previous_hash=parent_hash; snapshot_hash=await save_world_version(session,simulation_id,tick,snapshot,parent_hash=previous_hash,dataset_version='live'); parent_hash=snapshot_hash; phase['snapshot']={'state_hash':snapshot_hash,'parent_hash':previous_hash}; history.append(snapshot)
        tick_context.phase_results.update(phase)
        if broadcast: await broadcast({'type':'tick_completed','simulation_id':simulation_id,'tick':tick,'state':snapshot,'phase':phase,'changes':changes})
    run.status='completed'; run.ticks=ticks; run.events_ingested=len(raw_events or []); run.events_new=len(normalized); run.finished_at=datetime.now(timezone.utc); await session.commit(); return {'simulation_id':simulation_id,'ticks':ticks,'history':history}
