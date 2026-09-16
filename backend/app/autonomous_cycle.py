from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from .db import SessionLocal
from .event_engine import normalize
from .event_store import apply_events, create_run, create_snapshot, finish_run, persist_events
from .actor_decision import decide_all
from .action_executor import execute_actions
from .models import SimulationRunModel, ActorModel, RelationshipModel, DecisionModel, ActionModel
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


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


async def run_cycle(query: str = 'geopolitics', max_records: int = 25) -> dict:
    run_id = f'live-{uuid4().hex}'
    started = datetime.now(timezone.utc)
    raw, source_errors = [], {}
    try:
        try:
            raw += await fetch_news(query=query, max_records=max_records)
        except Exception as exc:
            source_errors['gdelt'] = str(exc)
        try:
            raw += await fetch_indicators()
        except Exception as exc:
            source_errors['worldbank'] = str(exc)
        normalized = normalize(raw)
        async with SessionLocal() as session:
            run = await create_run(session, run_id, query)
            new_count, duplicate_count = await persist_events(session, normalized)
            event_changes = await apply_events(session, normalized)

            decisions = await decide_all(session, simulation_id=run_id)
            options = {}
            for d in decisions:
                options.setdefault(d['actor_id'], []).extend(d.get('options', []))
            rel_rows = (await session.execute(select(RelationshipModel))).scalars().all()
            relationships = {(r.source_actor_id, r.target_actor_id): r.diplomatic for r in rel_rows}
            interactions = build_interactions(options, relationships)
            strategic = apply_interaction_effects(options, interactions)

            # Game theory is advisory: it can revise the proposed strategy, but the
            # action executor remains the only component allowed to mutate state.
            action_ids = []
            for d in decisions:
                actor_options = strategic.get(d['actor_id'], [])
                if actor_options:
                    chosen = max(actor_options, key=lambda x: (float(x.get('expected_utility', 0)), -float(x.get('risk', 1))))
                    d['selected_action'] = chosen['action']
                    row = await session.get(DecisionModel, d['decision_id'])
                    if row is not None:
                        row.selected_action = chosen['action']
                    action = await session.get(ActionModel, d['action_id'])
                    if action is not None:
                        action.action_type = chosen['action']
                action_ids.append(d['action_id'])
            actions = await execute_actions(session, action_ids)

            rows = (await session.execute(select(ActorModel))).scalars().all()
            states = {r.id: {'economic_capacity': r.economic_capacity, 'stability': r.stability, 'domestic_pressure': r.domestic_pressure} for r in rows}
            economy = economic_run(states)
            social = social_run(states)
            energy = energy_run(states)
            conflict = conflict_run(states)
            complexity = {a: complex_step(s).__dict__ for a, s in states.items()}
            forecasts = {
                a: forecast(f'{a}:stability', s,
                            {'social_unrest': -social[a].unrest, 'economic_growth': economy[a].growth,
                             'conflict_pressure': -conflict[a].escalation}, 5, 1)
                for a, s in states.items()
            }
            trade_edges = [
                {'source': r.source_actor_id, 'target': r.target_actor_id,
                 'value': max(0.0, r.trade), 'dependency': max(0.0, min(1.0, (1.0 - r.economic) / 2.0))}
                for r in rel_rows if r.trade != 0
            ]
            trade = trade_run(trade_edges)

            # Apply only bounded, deterministic engine deltas; no engine receives raw text.
            engine_changes = {}
            for actor in rows:
                deltas = {}
                for result in (economy[actor.id], social[actor.id], energy[actor.id], conflict[actor.id]):
                    for field, delta in result.changes.items():
                        old = getattr(actor, field)
                        new = _clamp(old + float(delta))
                        setattr(actor, field, new)
                        deltas[field] = deltas.get(field, 0.0) + (new - old)
                engine_changes[actor.id] = deltas

            all_changes = {**event_changes, 'engines': engine_changes}
            event_ids = [e.event_id for e in normalized]
            await create_snapshot(session, run_id, 1, all_changes, event_ids)
            await finish_run(session, run, len(raw), new_count, duplicate_count)
            await session.commit()

        return {
            'simulation_id': run_id, 'status': 'completed',
            'started_at': started.isoformat(), 'finished_at': datetime.now(timezone.utc).isoformat(),
            'normalized_events': len(normalized), 'new_events': new_count, 'duplicates': duplicate_count,
            'source_errors': source_errors, 'state_changes': all_changes,
            'game_interactions': [i.__dict__ for i in interactions], 'strategic_options': strategic,
            'decisions': decisions, 'actions': actions,
            'economic': {a: r.__dict__ for a, r in economy.items()},
            'trade': trade, 'energy': {a: r.__dict__ for a, r in energy.items()},
            'social': {a: r.__dict__ for a, r in social.items()},
            'conflict': {a: r.__dict__ for a, r in conflict.items()},
            'complex_systems': complexity, 'forecasts': forecasts,
        }
    except Exception:
        async with SessionLocal() as session:
            run = await session.get(SimulationRunModel, run_id)
            if run is not None:
                run.status = 'failed'
                run.finished_at = datetime.now(timezone.utc)
                await session.commit()
        raise
