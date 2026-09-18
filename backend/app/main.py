from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .db import init_db, get_db, SessionLocal
from .models import ActorModel, SimulationRunModel, SimulationTickModel
from .simulation import run_simulation
from .ingestion_service import sync_sources
import asyncio
from .realtime_pipeline import scheduler_loop, process_queue
from .stage5_service import Stage5Service
from .scenario_engine import ScenarioEngine
from .ws import ConnectionHub
from .world_service import WorldRuntime, WorldEvent

_scheduler_task = None
_scheduler_stop = asyncio.Event()
app = FastAPI(title='WORLD ENGINE API', version='2.0.0')
_stage5 = Stage5Service()
_hub = ConnectionHub()
_world = WorldRuntime()

@app.on_event('startup')
async def startup():
    global _scheduler_task
    await init_db()
    if not _scheduler_task:
        _scheduler_task = asyncio.create_task(scheduler_loop(SessionLocal, interval_seconds=900, stop_event=_scheduler_stop))

@app.get('/health')
async def health():
    return {'status': 'ok', 'engine': 'world-engine-v2'}

@app.get('/api/world/state')
async def world_state():
    return _world.snapshot()

@app.post('/api/events')
async def create_event(payload: dict):
    event = WorldEvent.from_payload(payload)
    result = _world.apply_event(event)
    await _hub.broadcast("live", {"type": "world_event", "event_id": event.event_id, "changes": result["changes"]})
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
    return await run_simulation(db, ticks=ticks, seed=seed, simulation_id=simulation_id, broadcast=lambda payload: _hub.broadcast(payload['simulation_id'], payload))

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
            await _hub.broadcast(simulation_id, {'type': 'client_message', 'simulation_id': simulation_id, 'payload': message})
    except WebSocketDisconnect:
        _hub.disconnect(simulation_id, websocket)

@app.get('/api/simulations/{simulation_id}/ticks')
async def simulation_ticks(simulation_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SimulationTickModel).where(SimulationTickModel.simulation_id == simulation_id).order_by(SimulationTickModel.tick))).scalars().all()
    return [{'tick': r.tick, 'state_changes': r.state_changes, 'phase_log': r.phase_log} for r in rows]

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
    if _scheduler_task:
        await _scheduler_task
