from __future__ import annotations
from datetime import datetime, timezone
from typing import List
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from .action_executor import execute_action
from .actor_decision import decide, decide_all
from .autonomous_cycle import run_cycle
from .db import get_db
from .init_db import init_db
from .models import ActionModel, ActorModel, CountryModel, DecisionModel, EventModel, RelationshipModel
from .schemas import Actor, EventCreate, WorldStateResponse

app = FastAPI(title="WORLD ENGINE API", version="0.8.0")

class Country(BaseModel):
    id: str
    name: str
    actor_id: str | None = None
    region: str | None = None

class Relationship(BaseModel):
    source_actor_id: str
    target_actor_id: str
    diplomatic: float = Field(0, ge=-1, le=1)
    economic: float = Field(0, ge=-1, le=1)
    military: float = Field(0, ge=-1, le=1)
    trade: float = Field(0, ge=-1, le=1)
    energy: float = Field(0, ge=-1, le=1)
    technology: float = Field(0, ge=-1, le=1)
    political: float = Field(0, ge=-1, le=1)
    information: float = Field(0, ge=-1, le=1)

@app.on_event("startup")
async def startup() -> None:
    await init_db()

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "world-engine-api", "version": app.version}

async def _actors(session: AsyncSession) -> List[Actor]:
    rows = (await session.execute(select(ActorModel).order_by(ActorModel.id))).scalars().all()
    return [Actor.model_validate(row, from_attributes=True) for row in rows]

@app.get("/api/world/state", response_model=WorldStateResponse)
async def get_world_state(session: AsyncSession = Depends(get_db)) -> WorldStateResponse:
    actors = await _actors(session)
    return WorldStateResponse(tick=0, timestamp=datetime.now(timezone.utc), actors={a.id: a for a in actors})

@app.get("/api/actors", response_model=List[Actor])
async def list_actors(session: AsyncSession = Depends(get_db)) -> List[Actor]:
    return await _actors(session)

@app.get("/api/actors/{actor_id}", response_model=Actor)
async def get_actor(actor_id: str, session: AsyncSession = Depends(get_db)) -> Actor:
    actor = await session.get(ActorModel, actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return Actor.model_validate(actor, from_attributes=True)

@app.get("/api/countries", response_model=List[Country])
async def list_countries(session: AsyncSession = Depends(get_db)) -> List[Country]:
    rows = (await session.execute(select(CountryModel).order_by(CountryModel.id))).scalars().all()
    return [Country.model_validate(row, from_attributes=True) for row in rows]

@app.get("/api/relationships", response_model=List[Relationship])
async def list_relationships(session: AsyncSession = Depends(get_db)) -> List[Relationship]:
    rows = (await session.execute(select(RelationshipModel).order_by(RelationshipModel.id))).scalars().all()
    return [Relationship.model_validate(row, from_attributes=True) for row in rows]

@app.get("/api/events")
async def list_events(limit: int = 50, session: AsyncSession = Depends(get_db)) -> list[dict]:
    limit = max(1, min(limit, 250))
    rows = (await session.execute(select(EventModel).order_by(desc(EventModel.event_timestamp)).limit(limit))).scalars().all()
    return [{"event_id": r.id, "event_type": r.event_type, "title": r.title, "description": r.description, "timestamp": r.event_timestamp.isoformat(), "confidence": r.confidence, "status": r.status, "source_count": r.source_count, "metadata": r.metadata_json} for r in rows]

@app.post("/api/events", response_model=WorldStateResponse)
async def ingest_event(event: EventCreate, session: AsyncSession = Depends(get_db)) -> WorldStateResponse:
    for actor_id in event.actor_ids:
        if await session.get(ActorModel, actor_id) is None:
            raise HTTPException(status_code=400, detail=f"Unknown actor: {actor_id}")
    for actor_id in event.actor_ids:
        actor = await session.get(ActorModel, actor_id)
        actor.stability = max(0, min(1, actor.stability + event.impact.get("stability", 0)))
        actor.domestic_pressure = max(0, min(1, actor.domestic_pressure + event.impact.get("domestic_pressure", 0)))
    await session.commit()
    return await get_world_state(session)

@app.post("/api/actors/{actor_id}/decide")
async def actor_decision(actor_id: str, simulation_id: str | None = None, session: AsyncSession = Depends(get_db)) -> dict:
    try:
        result = await decide(session, actor_id, simulation_id=simulation_id)
        await session.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/api/engine/decisions")
async def engine_decisions(simulation_id: str | None = None, session: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await decide_all(session, simulation_id=simulation_id)
    await session.commit()
    return result

@app.get("/api/decisions")
async def list_decisions(limit: int = 50, session: AsyncSession = Depends(get_db)) -> list[dict]:
    limit = max(1, min(limit, 250))
    rows = (await session.execute(select(DecisionModel).order_by(desc(DecisionModel.created_at)).limit(limit))).scalars().all()
    return [{"decision_id": r.id, "actor_id": r.actor_id, "simulation_id": r.simulation_id, "selected_action": r.selected_action, "confidence": r.confidence, "situation": r.situation, "reasoning_factors": r.reasoning_factors, "options": r.options, "information_state": r.information_state, "created_at": r.created_at.isoformat()} for r in rows]

@app.get("/api/actions")
async def list_actions(limit: int = 50, session: AsyncSession = Depends(get_db)) -> list[dict]:
    limit = max(1, min(limit, 250))
    rows = (await session.execute(select(ActionModel).order_by(desc(ActionModel.created_at)).limit(limit))).scalars().all()
    return [{"action_id": r.id, "decision_id": r.decision_id, "actor_id": r.actor_id, "action_type": r.action_type, "status": r.status, "effects": r.effects, "created_at": r.created_at.isoformat()} for r in rows]

@app.post("/api/actions/{action_id}/execute")
async def execute(action_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    try:
        result = await execute_action(session, action_id)
        await session.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/api/engine/cycle")
async def autonomous_cycle(query: str = "geopolitics", max_records: int = 25) -> dict:
    return await run_cycle(query=query, max_records=max_records)
