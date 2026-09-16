from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from .db import SessionLocal
from .event_engine import normalize
from .event_store import apply_events, create_run, create_snapshot, finish_run, persist_events
from .actor_decision import decide_all
from .action_executor import execute_actions
from .models import SimulationRunModel, ActorModel, RelationshipModel
from .sources.gdelt import fetch_news
from .sources.worldbank import fetch_indicators
from .game_theory import build_interactions, apply_interaction_effects
from .economic_engine import run as economic_run
from .trade_engine import network as trade_run
from .energy_engine import run as energy_run
from .social_engine import run as social_run
from .conflict_engine import run as conflict_run
from .complex_systems import step as complex_step
from .forecasting_engine import forecast

async def run_cycle(query: str = 'geopolitics', max_records: int = 25) -> dict:
    run_id=f'live-{uuid4().hex}'; started=datetime.now(timezone.utc); raw=[]; source_errors={}
    try:
        try: raw += await fetch_news(query=query,max_records=max_records)
        except Exception as exc: source_errors['gdelt']=str(exc)
        try: raw += await fetch_indicators()
        except Exception as exc: source_errors['worldbank']=str(exc)
        normalized=normalize(raw)
        async with SessionLocal() as session:
            run=await create_run(session,run_id,query)
            new_count,duplicate_count=await persist_events(session,normalized)
            changes=await apply_events(session,normalized)
            decisions=await decide_all(session,simulation_id=run_id)
            options={}
            for d in decisions:
                options.setdefault(d['actor_id'],[]).extend(d.get('options',[]))
            rels=await session.execute(RelationshipModel.__table__.select())
            relationships={(r.source_actor_id,r.target_actor_id):r.diplomatic for r in rels}
            interactions=build_interactions(options,relationships)
            strategic=apply_interaction_effects(options,interactions)
            actions=await execute_actions(session,[d['action_id'] for d in decisions])
            rows=(await session.execute(ActorModel.__table__.select())).mappings().all()
            states={r['id']:{'economic_capacity':r['economic_capacity'],'stability':r['stability'],'domestic_pressure':r['domestic_pressure']} for r in rows}
            economy=economic_run(states)
            social=social_run(states)
            energy=energy_run(states)
            complexity={a:complex_step(s).__dict__ for a,s in states.items()}
            forecasts={a:forecast(f'{a}:stability',s,{'social_unrest':-social[a].unrest,'economic_growth':economy[a].growth},5,1) for a,s in states.items()}
            trade=trade_run([])
            event_ids=[e.event_id for e in normalized]
            engine_changes={'economic':{a:r.changes for a,r in economy.items()},'social':{a:r.changes for a,r in social.items()},'energy':{a:r.changes for a,r in energy.items()},'complex_systems':complexity,'trade':trade}
            await create_snapshot(session,run_id,1,{**changes,**engine_changes},event_ids)
            await finish_run(session,run,len(raw),new_count,duplicate_count); await session.commit()
        return {'simulation_id':run_id,'status':'completed','started_at':started.isoformat(),'finished_at':datetime.now(timezone.utc).isoformat(),'normalized_events':len(normalized),'new_events':new_count,'duplicates':duplicate_count,'source_errors':source_errors,'state_changes':changes,'game_interactions':[i.__dict__ for i in interactions],'strategic_options':strategic,'decisions':decisions,'actions':actions,'economic':{a:r.__dict__ for a,r in economy.items()},'social':{a:r.__dict__ for a,r in social.items()},'energy':{a:r.__dict__ for a,r in energy.items()},'complex_systems':complexity,'forecasts':forecasts}
    except Exception:
        async with SessionLocal() as session:
            run=await session.get(SimulationRunModel,run_id)
            if run is not None: run.status='failed'; run.finished_at=datetime.now(timezone.utc); await session.commit()
        raise
