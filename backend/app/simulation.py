from __future__ import annotations
from uuid import uuid4
from datetime import datetime, timezone
from .models import SimulationRunModel, ActorPerceptionModel, EffectModel, ForecastModel
from .integration_state import load_world_state, sync_world_state_to_db, persist_tick
from .event_engine import normalize
from .decision_engine import decide_all
from .action_executor import execute_actions
from .cascade_engine import CascadeEngine
from .perception_engine import PerceptionEngine
from .forecasting_engine import forecast
from .engines import economic, social, conflict, energy
from .realtime_pipeline import save_world_version
from .simulation_tick import TickContext

async def run_simulation(session, ticks=5, seed=0, simulation_id=None, raw_events=None, broadcast=None):
    ticks = max(1, min(120, int(ticks)))
    simulation_id = simulation_id or f'sim-{uuid4().hex}'
    run = SimulationRunModel(id=simulation_id, mode='simulation', status='running', query='local')
    session.add(run)
    await session.flush()

    state = await load_world_state(session, simulation_id, 0, seed)
    normalized = normalize(raw_events or [])
    event_ids = [event.event_id for event in normalized]
    from .event_store import persist_events
    await persist_events(session, normalized)

    history = []
    parent_hash = None
    for tick in range(1, ticks + 1):
        state.tick = tick
        phase, changes = {}, {}
        TickContext(simulation_id, tick, seed + tick)
        pe = PerceptionEngine()
        for actor_id, actor in state.actors.items():
            facts = [
                {
                    'fact_id': event.event_id,
                    'value': event.description,
                    'confidence': event.confidence,
                    'source_ids': [source.get('source_id', 'unknown') for source in (event.metadata or {}).get('sources', [])],
                }
                for event in normalized
            ]
            perception = pe.build(actor_id, facts, actor.values.get('information_quality', 0.7))
            session.add(ActorPerceptionModel(
                simulation_id=simulation_id, tick=tick, actor_id=actor_id,
                facts_json={key: value.__dict__ for key, value in perception.facts.items()},
            ))

        decisions = await decide_all(session, simulation_id)
        phase['perception'] = len(state.actors)
        phase['decision'] = len(decisions)
        actions = await execute_actions(session, [decision['action_id'] for decision in decisions])
        phase['action'] = actions

        adjacency = {}
        for key in state.metadata.get('relationships', {}):
            source, target = key.split(':', 1)
            adjacency.setdefault(source, []).append(target)

        # Action execution already updates the database actor values. Only
        # engine-generated deltas are applied to the in-memory state here.
        cascaded, truncated = CascadeEngine().run([], adjacency)
        phase['cascade'] = {'count': len(cascaded), 'truncated': truncated}
        for effect in cascaded:
            state.apply_delta(effect.target, effect.field, effect.delta)
            session.add(EffectModel(
                simulation_id=simulation_id, tick=tick, source=effect.source,
                target=effect.target, field=effect.field, delta=effect.delta,
                confidence=effect.confidence, depth=effect.depth, mechanism=effect.mechanism,
            ))

        state_results = {actor_id: actor for actor_id, actor in state.actors.items()}
        for bundle in (economic(state_results), social(state_results), energy(state_results), conflict(state_results)):
            for actor_id, result in bundle.items():
                for field, delta in result.changes.items():
                    state.apply_delta(actor_id, field, delta)
                    changes.setdefault(actor_id, {})[field] = changes.setdefault(actor_id, {}).get(field, 0) + delta
        phase['engines'] = changes

        for actor_id, actor in state.actors.items():
            prediction = forecast(
                f'{actor_id}:stability',
                actor.values,
                {'economic': changes.get(actor_id, {}).get('economic_capacity', 0),
                 'social': changes.get(actor_id, {}).get('domestic_pressure', 0) * -0.5},
                5, seed + tick,
            )
            probabilities = prediction['probabilities']
            expected = (
                probabilities['low'] * 0.25
                + probabilities['medium'] * 0.50
                + probabilities['high'] * 0.75
            )
            uncertainty = prediction['uncertainty']
            session.add(ForecastModel(
                simulation_id=simulation_id, tick=tick, target=prediction['target'],
                horizon=prediction['horizon'], expected=expected,
                lower=max(0.0, expected - uncertainty),
                upper=min(1.0, expected + uncertainty),
                confidence=max(0.0, 1.0 - uncertainty),
                drivers={'drivers': prediction['drivers'], 'probabilities': probabilities},
            ))

        await sync_world_state_to_db(session, state)
        await persist_tick(session, simulation_id, state, changes, event_ids, phase)
        snapshot = state.snapshot()
        previous_hash = parent_hash
        snapshot_hash = await save_world_version(
            session, simulation_id, tick, snapshot,
            parent_hash=previous_hash, dataset_version='live',
        )
        parent_hash = snapshot_hash
        phase['snapshot'] = {'state_hash': snapshot_hash, 'parent_hash': previous_hash}
        history.append(snapshot)
        if broadcast:
            await broadcast({'type': 'tick_completed', 'simulation_id': simulation_id,
                             'tick': tick, 'state': snapshot, 'phase': phase, 'changes': changes})

    run.status = 'completed'
    run.ticks = ticks
    run.events_ingested = len(raw_events or [])
    run.events_new = len(normalized)
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()
    return {'simulation_id': simulation_id, 'ticks': ticks, 'history': history}
