from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from .db import init_db, get_db, SessionLocal
from .models import ActorModel, SimulationRunModel, SimulationTickModel
from .simulation import run_simulation
from .ingestion_service import sync_sources
import asyncio
import os
from .realtime_pipeline import process_queue
from .stage5_service import Stage5Service
from .scenario_engine import ScenarioEngine
from .ws import ConnectionHub
from .world_service import WorldRuntime, WorldEvent
from .strategic_overview import strategic_overview
from .game_turn import play_turn
from .live_intelligence import (
    get_live_state_snapshot,
    live_intelligence_loop,
    live_state,
    recent_live_events,
    run_live_intelligence_cycle,
)
from .live_outlook import build_live_outlook
from .prediction_center import build_prediction_center
from .operations_center import build_operations_center, set_alert_state
from .runtime_bus import runtime_bus
from .strategic_gameplay import (
    actor_detail,
    causal_chain,
    crisis_detail,
    scenario_tree_detail,
    submit_player_action,
)

_scheduler_task = None
_scheduler_stop = asyncio.Event()
_bus_task = None
_bus_stop = asyncio.Event()

app = FastAPI(title='WORLD ENGINE API', version='2.1.0')

_allowed_origins = [
    item.strip()
    for item in os.getenv(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:5173,https://geopolitica20261.netlify.app',
    ).split(',')
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)
_stage5 = Stage5Service()
_hub = ConnectionHub()
_world = WorldRuntime()

async def _deliver_runtime_payload(payload: dict):
    simulation_id = str(payload.get('simulation_id') or 'live')
    await _hub.broadcast(simulation_id, payload)


async def _broadcast_payload(payload: dict):
    if runtime_bus.enabled:
        await runtime_bus.publish(payload)
    else:
        await _deliver_runtime_payload(payload)


@app.on_event('startup')
async def startup():
    global _scheduler_task, _bus_task

    if os.getenv('AUTO_CREATE_SCHEMA', '1').lower() in {'1', 'true', 'yes'}:
        await init_db()

    if runtime_bus.enabled and _bus_task is None:
        _bus_task = asyncio.create_task(
            runtime_bus.subscribe(_deliver_runtime_payload, _bus_stop)
        )

    if (
        os.getenv('EMBEDDED_LIVE_SCHEDULER', '0').lower() in {'1', 'true', 'yes'}
        and _scheduler_task is None
    ):
        _scheduler_task = asyncio.create_task(
            live_intelligence_loop(
                broadcast=_broadcast_payload,
                stop_event=_scheduler_stop,
            )
        )


@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'engine': 'world-engine-v2.1',
        'role': os.getenv('APP_ROLE', 'api'),
        'runtime_bus': 'redis' if runtime_bus.enabled else 'local',
        'live_intelligence': await get_live_state_snapshot(),
    }


@app.get('/health/live')
async def health_live():
    return {'status': 'ok', 'role': os.getenv('APP_ROLE', 'api')}


@app.get('/health/ready')
async def health_ready(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text('SELECT 1'))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'database unavailable: {exc}') from exc

    return {
        'status': 'ready',
        'database': 'ok',
    }


@app.get('/health/dependencies')
async def health_dependencies(db: AsyncSession = Depends(get_db)):
    result = {
        'status': 'ok',
        'database': 'unknown',
        'redis': 'disabled' if not runtime_bus.enabled else 'unknown',
        'redis_error': None,
    }

    try:
        await db.execute(text('SELECT 1'))
        result['database'] = 'ok'
    except Exception as exc:
        result['database'] = 'error'
        result['status'] = 'degraded'
        result['database_error'] = str(exc)

    if runtime_bus.enabled:
        try:
            result['redis'] = 'ok' if await runtime_bus.ping() else 'error'
            if result['redis'] != 'ok':
                result['status'] = 'degraded'
        except Exception as exc:
            result['redis'] = 'error'
            result['redis_error'] = str(exc)
            result['status'] = 'degraded'

    return result

@app.get('/api/world/state')
async def world_state():
    return _world.snapshot()

@app.post('/api/events')
async def create_event(payload: dict):
    event = WorldEvent.from_payload(payload)
    result = _world.apply_event(event)
    await _broadcast_payload({
        "type": "world_event",
        "simulation_id": "live",
        "event_id": event.event_id,
        "changes": result["changes"],
    })
    return result

@app.get('/api/events')
async def list_events():
    return _world.events()

@app.get('/api/actors')
async def actors(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ActorModel).order_by(ActorModel.id))).scalars().all()
    return [{'id': r.id, 'name': r.name, 'stability': r.stability, 'economic_capacity': r.economic_capacity, 'domestic_pressure': r.domestic_pressure} for r in rows]

@app.post('/api/simulations')
async def simulations(ticks: int = 5, seed: int = 0, simulation_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return await run_simulation(
        db,
        ticks=ticks,
        seed=seed,
        simulation_id=simulation_id,
        broadcast=_broadcast_payload,
    )

@app.get('/api/simulations')
async def simulation_list(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SimulationRunModel).order_by(SimulationRunModel.started_at.desc()))).scalars().all()
    return [{'id': r.id, 'status': r.status, 'ticks': r.ticks} for r in rows]

@app.get('/api/knowledge-graph/summary')
async def knowledge_graph_summary():
    return _stage5.summary()

@app.get('/api/knowledge-graph')
async def knowledge_graph():
    return _stage5.graph.export()

@app.post('/api/scenarios/counterfactual')
async def counterfactual(payload: dict):
    result = ScenarioEngine().run(payload.get('baseline', {}), payload.get('assumptions', []), payload.get('ticks', 5), payload.get('scenario_id', 'scenario'))
    return result.__dict__

@app.websocket('/ws/simulation/{simulation_id}')
async def simulation_socket(websocket: WebSocket, simulation_id: str):
    await _hub.connect(simulation_id, websocket)
    try:
        await websocket.send_json({'type': 'connected', 'simulation_id': simulation_id})
        while True:
            message = await websocket.receive_json()
            await _broadcast_payload({
                'type': 'client_message',
                'simulation_id': simulation_id,
                'payload': message,
            })
    except WebSocketDisconnect:
        _hub.disconnect(simulation_id, websocket)

@app.get('/api/simulations/{simulation_id}/ticks')
async def simulation_ticks(simulation_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SimulationTickModel).where(SimulationTickModel.simulation_id == simulation_id).order_by(SimulationTickModel.tick))).scalars().all()
    return [{'tick': r.tick, 'state_changes': r.state_changes, 'phase_log': r.phase_log} for r in rows]

@app.get('/api/simulations/{simulation_id}/strategic-overview')
async def simulation_strategic_overview(simulation_id: str, db: AsyncSession = Depends(get_db)):
    return await strategic_overview(db, simulation_id)

@app.get('/api/simulations/{simulation_id}/actors/{actor_id}')
async def simulation_actor_detail(simulation_id: str, actor_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await actor_detail(db, simulation_id, actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.get('/api/simulations/{simulation_id}/crises/{crisis_id}')
async def simulation_crisis_detail(simulation_id: str, crisis_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await crisis_detail(db, simulation_id, crisis_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.get('/api/simulations/{simulation_id}/scenario-tree/{actor_id}')
async def simulation_scenario_tree(
    simulation_id: str,
    actor_id: str,
    depth: int = 3,
    branching: int = 3,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scenario_tree_detail(db, simulation_id, actor_id, depth, branching)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.get('/api/simulations/{simulation_id}/causal-chain')
async def simulation_causal_chain(
    simulation_id: str,
    limit: int = 120,
    db: AsyncSession = Depends(get_db),
):
    return await causal_chain(db, simulation_id, limit)

@app.post('/api/simulations/{simulation_id}/turns')
async def simulation_turn(
    simulation_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await play_turn(
            db,
            parent_simulation_id=simulation_id,
            actor_id=str(payload.get('actor_id') or ''),
            action_type=str(payload.get('action_type') or ''),
            target_actor_id=(
                str(payload.get('target_actor_id'))
                if payload.get('target_actor_id') else None
            ),
            seed=int(payload.get('seed', 0)),
            action_points=int(payload.get('action_points', 2)),
            broadcast=_broadcast_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.get('/api/live-intelligence/status')
async def live_intelligence_status():
    return await get_live_state_snapshot()

@app.get('/api/live-intelligence/events')
async def live_intelligence_events(limit: int = 50):
    return await recent_live_events(max(1, min(200, int(limit))))

@app.get('/api/live-intelligence/outlook')
async def live_intelligence_outlook(db: AsyncSession = Depends(get_db)):
    state = await get_live_state_snapshot()
    return await build_live_outlook(db, state.get('last_simulation_id'))

@app.get('/api/live-intelligence/prediction-center')
async def live_prediction_center(db: AsyncSession = Depends(get_db)):
    state = await get_live_state_snapshot()
    simulation_id = state.get('last_simulation_id')
    if not simulation_id:
        return {
            'simulation_id': None,
            'status': 'no_live_simulation',
            'horizons': [1, 7, 30],
            'actors': [],
            'scenario_matrix': [],
            'causal_graph': {'nodes': [], 'edges': []},
            'calibration': {'scored_targets': 0, 'mean_brier': None, 'quality': 'unscored'},
        }
    return await build_prediction_center(db, simulation_id)

@app.get('/api/simulations/{simulation_id}/prediction-center')
async def simulation_prediction_center(
    simulation_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await build_prediction_center(db, simulation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get('/api/simulations/{simulation_id}/operations-center')
async def simulation_operations_center(
    simulation_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await build_operations_center(db, simulation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post('/api/simulations/{simulation_id}/alerts/{alert_id}/state')
async def simulation_alert_state(
    simulation_id: str,
    alert_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await set_alert_state(
            db,
            simulation_id,
            alert_id,
            status=str(payload.get('status') or 'acknowledged'),
            acknowledged_by=(
                str(payload.get('acknowledged_by'))
                if payload.get('acknowledged_by') else None
            ),
            note=str(payload.get('note')) if payload.get('note') else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get('/api/live-intelligence/operations-center')
async def live_operations_center(db: AsyncSession = Depends(get_db)):
    simulation_id = live_state.last_simulation_id
    if not simulation_id:
        return {
            'simulation_id': None,
            'status': 'no_live_simulation',
            'tick': 0,
            'posture': 'normal',
            'summary': {
                'critical': 0,
                'high': 0,
                'medium': 0,
                'low': 0,
                'open': 0,
                'acknowledged': 0,
                'total': 0,
            },
            'alerts': [],
            'brief': {
                'headline': 'No live simulation is available yet.',
                'top_priorities': [],
                'watch_actors': [],
                'watch_crises': [],
                'forecast_calibration': {},
                'generated_from_tick': 0,
            },
        }
    return await build_operations_center(db, simulation_id)

@app.post('/api/live-intelligence/run-now')
async def live_intelligence_run_now():
    return await run_live_intelligence_cycle(
        broadcast=_broadcast_payload,
        force_simulation=True,
    )

@app.post('/api/simulations/{simulation_id}/player-actions')
async def simulation_player_action(
    simulation_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await submit_player_action(
            db,
            simulation_id=simulation_id,
            actor_id=str(payload.get('actor_id') or ''),
            action_type=str(payload.get('action_type') or ''),
            target_actor_id=(
                str(payload.get('target_actor_id'))
                if payload.get('target_actor_id') else None
            ),
            rationale=str(payload.get('rationale') or 'player_selected'),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@app.post('/api/ingestion/sync')
async def ingestion_sync(query: str = 'geopolitics', max_records: int = 25, db: AsyncSession = Depends(get_db)):
    return await sync_sources(db, query=query, max_records=max(1, min(100, int(max_records))))

@app.post('/api/ingestion/process-queue')
async def ingestion_process_queue(limit: int = 10, db: AsyncSession = Depends(get_db)):
    return {'processed': await process_queue(db, max(1, min(100, int(limit))))}

@app.get('/api/world-state/versions/{simulation_id}')
async def world_state_versions(simulation_id: str, db: AsyncSession = Depends(get_db)):
    from .models import WorldStateVersionModel
    rows = (await db.execute(select(WorldStateVersionModel).where(WorldStateVersionModel.simulation_id == simulation_id).order_by(WorldStateVersionModel.tick))).scalars().all()
    return [{'tick': r.tick, 'state_hash': r.state_hash, 'parent_hash': r.parent_hash, 'dataset_version': r.dataset_version, 'created_at': r.created_at} for r in rows]

@app.on_event('shutdown')
async def shutdown():
    _scheduler_stop.set()
    _bus_stop.set()

    if _scheduler_task:
        await _scheduler_task
    if _bus_task:
        await _bus_task

    await runtime_bus.close()
