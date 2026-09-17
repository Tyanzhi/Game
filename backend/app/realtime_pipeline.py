"""Durable ingestion queue, scheduler, and reproducible world-state versions."""
from __future__ import annotations
import asyncio, hashlib, json
from datetime import datetime, timezone
from sqlalchemy import select
from .models import IngestionQueueModel, WorldStateVersionModel
from .ingestion_service import sync_sources

class EventQueue:
    async def enqueue(self, session, payload: dict):
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        row = IngestionQueueModel(dedupe_key=key, payload=payload, status='pending')
        session.add(row); await session.flush(); return row

async def process_queue(session, limit=10):
    rows=(await session.execute(select(IngestionQueueModel).where(IngestionQueueModel.status=='pending').order_by(IngestionQueueModel.created_at).limit(limit))).scalars().all()
    processed=0
    for row in rows:
        row.status='processing'
        try:
            await sync_sources(session, query=row.payload.get('query','geopolitics'), max_records=row.payload.get('max_records',25))
            row.status='done'; row.processed_at=datetime.now(timezone.utc); processed += 1
        except Exception as exc:
            row.status='failed'; row.error=str(exc)[:2000]
    await session.commit(); return processed

async def scheduler_loop(session_factory, interval_seconds=900, stop_event=None):
    stop_event=stop_event or asyncio.Event()
    while not stop_event.is_set():
        async with session_factory() as session:
            q=EventQueue(); await q.enqueue(session, {'query':'geopolitics','max_records':25, 'scheduled_at': datetime.now(timezone.utc).isoformat()}); await session.commit()
            await process_queue(session)
        try: await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError: pass

def state_hash(state: dict) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',',':'), default=str).encode()).hexdigest()

async def save_world_version(session, simulation_id, tick, state, parent_hash=None, dataset_version='live'):
    digest=state_hash(state)
    row=WorldStateVersionModel(simulation_id=simulation_id,tick=tick,state_hash=digest,parent_hash=parent_hash,dataset_version=dataset_version,state_json=state)
    session.add(row); await session.flush(); return digest
