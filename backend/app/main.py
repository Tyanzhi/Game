from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="WORLD ENGINE API", version="0.1.0")


class Actor(BaseModel):
    id: str
    name: str
    actor_type: str = "state"
    stability: float = Field(0.7, ge=0, le=1)
    economic_capacity: float = Field(0.7, ge=0, le=1)
    diplomatic_capacity: float = Field(0.7, ge=0, le=1)
    security_capacity: float = Field(0.7, ge=0, le=1)
    domestic_pressure: float = Field(0.3, ge=0, le=1)


class WorldState(BaseModel):
    tick: int = 0
    timestamp: datetime
    actors: Dict[str, Actor]


class EventIn(BaseModel):
    event_id: str
    event_type: str
    actor_ids: List[str]
    impact: Dict[str, float] = {}
    confidence: float = Field(1.0, ge=0, le=1)


actors: Dict[str, Actor] = {
    "usa": Actor(id="usa", name="United States"),
    "chn": Actor(id="chn", name="China"),
    "rus": Actor(id="rus", name="Russia"),
}

world = WorldState(
    tick=0,
    timestamp=datetime.now(timezone.utc),
    actors=actors,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "world-engine-api", "version": "0.1.0"}


@app.get("/api/world/state", response_model=WorldState)
def get_world_state() -> WorldState:
    return world


@app.get("/api/actors", response_model=List[Actor])
def list_actors() -> List[Actor]:
    return list(world.actors.values())


@app.get("/api/actors/{actor_id}", response_model=Actor)
def get_actor(actor_id: str) -> Actor:
    actor = world.actors.get(actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return actor


@app.post("/api/events", response_model=WorldState)
def ingest_event(event: EventIn) -> WorldState:
    for actor_id in event.actor_ids:
        if actor_id not in world.actors:
            raise HTTPException(status_code=400, detail=f"Unknown actor: {actor_id}")

    for actor_id in event.actor_ids:
        actor = world.actors[actor_id]
        actor.stability = max(0, min(1, actor.stability + event.impact.get("stability", 0)))
        actor.domestic_pressure = max(
            0, min(1, actor.domestic_pressure + event.impact.get("domestic_pressure", 0))
        )

    world.tick += 1
    world.timestamp = datetime.now(timezone.utc)
    return world
