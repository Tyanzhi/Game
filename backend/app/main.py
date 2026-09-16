from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .init_db import init_db
from .models import ActorModel
from .schemas import Actor, EventCreate, WorldStateResponse

app = FastAPI(title="WORLD ENGINE API", version="0.3.0")


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
    return WorldStateResponse(
        tick=0,
        timestamp=datetime.now(timezone.utc),
        actors={actor.id: actor for actor in actors},
    )


@app.get("/api/actors", response_model=List[Actor])
async def list_actors(session: AsyncSession = Depends(get_db)) -> List[Actor]:
    return await _actors(session)


@app.get("/api/actors/{actor_id}", response_model=Actor)
async def get_actor(actor_id: str, session: AsyncSession = Depends(get_db)) -> Actor:
    actor = await session.get(ActorModel, actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return Actor.model_validate(actor, from_attributes=True)


@app.post("/api/events", response_model=WorldStateResponse)
async def ingest_event(event: EventCreate, session: AsyncSession = Depends(get_db)) -> WorldStateResponse:
    actor_rows = []
    for actor_id in event.actor_ids:
        actor = await session.get(ActorModel, actor_id)
        if actor is None:
            raise HTTPException(status_code=400, detail=f"Unknown actor: {actor_id}")
        actor_rows.append(actor)

    for actor in actor_rows:
        actor.stability = max(0, min(1, actor.stability + event.impact.get("stability", 0)))
        actor.domestic_pressure = max(
            0, min(1, actor.domestic_pressure + event.impact.get("domestic_pressure", 0))
        )

    await session.commit()
    return await get_world_state(session)
