from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel, Field


class Actor(BaseModel):
    id: str
    name: str
    actor_type: str = "state"
    stability: float = Field(0.7, ge=0, le=1)
    economic_capacity: float = Field(0.7, ge=0, le=1)
    diplomatic_capacity: float = Field(0.7, ge=0, le=1)
    security_capacity: float = Field(0.7, ge=0, le=1)
    domestic_pressure: float = Field(0.3, ge=0, le=1)


class WorldStateResponse(BaseModel):
    tick: int
    timestamp: datetime
    actors: Dict[str, Actor]


class EventCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=64)
    actor_ids: List[str]
    impact: Dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(1.0, ge=0, le=1)
    status: str = Field("FACT", pattern="^(FACT|CLAIM|HYPOTHESIS)$")
