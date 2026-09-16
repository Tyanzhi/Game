from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from fastapi import FastAPI, HTTPException

from .schemas import Actor, EventCreate, WorldStateResponse

app = FastAPI(title="WORLD ENGINE API", version="0.2.0")

# In-memory projection is retained for the first vertical slice. SQL models
# are defined separately so persistence can be enabled without changing the API.
actors: Dict[str, Actor] = {
    "usa": Actor(id="usa", name="United States"),
    "chn": Actor(id="chn", name="China"),
    "rus": Actor(id="rus", name="Russia"),
}
world_tick = 0
world_timestamp = datetime.now(timezone.utc)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "world-engine-api", "version": app.version}


@app.get("/api/world/state", response_model=WorldStateResponse)
def get_world_state() -> WorldStateResponse:
    return WorldStateResponse(tick=world_tick, timestamp=world_timestamp, actors=actors)


@app.get("/api/actors", response_model=List[Actor])
def list_actors() -> List[Actor]:
    return list(actors.values())


@app.get("/api/actors/{actor_id}", response_model=Actor)
def get_actor(actor_id: str) -> Actor:
    actor = actors.get(actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor not found")
    return actor


@app.post("/api/events", response_model=WorldStateResponse)
def ingest_event(event: EventCreate) -> WorldStateResponse:
    global world_tick, world_timestamp

    for actor_id in event.actor_ids:
        if actor_id not in actors:
            raise HTTPException(status_code=400, detail=f"Unknown actor: {actor_id}")

    for actor_id in event.actor_ids:
        actor = actors[actor_id]
        actor.stability = max(0, min(1, actor.stability + event.impact.get("stability", 0)))
        actor.domestic_pressure = max(
            0, min(1, actor.domestic_pressure + event.impact.get("domestic_pressure", 0))
        )

    world_tick += 1
    world_timestamp = datetime.now(timezone.utc)
    return get_world_state()
