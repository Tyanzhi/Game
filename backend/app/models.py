from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, JSON, Integer, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class ActorModel(Base):
    __tablename__ = 'actors'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    actor_type: Mapped[str] = mapped_column(String(50), default='state')
    stability: Mapped[float] = mapped_column(Float, default=.7)
    economic_capacity: Mapped[float] = mapped_column(Float, default=.7)
    diplomatic_capacity: Mapped[float] = mapped_column(Float, default=.7)
    security_capacity: Mapped[float] = mapped_column(Float, default=.7)
    domestic_pressure: Mapped[float] = mapped_column(Float, default=.2)
    risk_tolerance: Mapped[float] = mapped_column(Float, default=.5)
    strategic_patience: Mapped[float] = mapped_column(Float, default=.5)
    escalation_threshold: Mapped[float] = mapped_column(Float, default=.6)
    information_quality: Mapped[float] = mapped_column(Float, default=.7)
    energy_security: Mapped[float] = mapped_column(Float, default=.7)
    trade_resilience: Mapped[float] = mapped_column(Float, default=.7)
    technological_capacity: Mapped[float] = mapped_column(Float, default=.7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class CountryModel(Base):
    __tablename__ = 'countries'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    region: Mapped[str] = mapped_column(String(100), default='')

class RelationshipModel(Base):
    __tablename__ = 'relationships'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_actor_id: Mapped[str] = mapped_column(String(64), index=True)
    target_actor_id: Mapped[str] = mapped_column(String(64), index=True)
    diplomatic: Mapped[float] = mapped_column(Float, default=0)
    economic: Mapped[float] = mapped_column(Float, default=0)
    military: Mapped[float] = mapped_column(Float, default=0)
    trade: Mapped[float] = mapped_column(Float, default=0)
    energy: Mapped[float] = mapped_column(Float, default=0)
    technology: Mapped[float] = mapped_column(Float, default=0)
    political: Mapped[float] = mapped_column(Float, default=0)
    information: Mapped[float] = mapped_column(Float, default=0)
    __table_args__ = (UniqueConstraint('source_actor_id', 'target_actor_id', name='uq_relationship_direction'),)

class EventModel(Base):
    __tablename__ = 'events'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(String(5000))
    event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=.5)
    status: Mapped[str] = mapped_column(String(30), default='FACT')
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class EventSourceModel(Base):
    __tablename__ = 'event_sources'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(100))
    source_url: Mapped[str] = mapped_column(String(2000), default='')
    source_title: Mapped[str] = mapped_column(String(500), default='')
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class SimulationRunModel(Base):
    __tablename__ = 'simulation_runs'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    mode: Mapped[str] = mapped_column(String(50), default='live')
    status: Mapped[str] = mapped_column(String(30), default='running')
    query: Mapped[str] = mapped_column(String(500), default='')
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events_ingested: Mapped[int] = mapped_column(Integer, default=0)
    events_new: Mapped[int] = mapped_column(Integer, default=0)
    events_deduplicated: Mapped[int] = mapped_column(Integer, default=0)
    ticks: Mapped[int] = mapped_column(Integer, default=0)

class SimulationTickModel(Base):
    __tablename__ = 'simulation_ticks'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(String(100), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(Integer, default=0)
    event_ids: Mapped[list] = mapped_column(JSON, default=list)
    state_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    phase_log: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('simulation_id', 'tick', name='uq_simulation_tick'),)

class WorldSnapshotModel(Base):
    __tablename__ = 'world_snapshots'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(String(100), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(50))
    dataset_version: Mapped[str] = mapped_column(String(100))
    random_seed: Mapped[int] = mapped_column(Integer, default=0)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('simulation_id', 'tick', name='uq_snapshot_tick'),)

class DecisionModel(Base):
    __tablename__ = 'decisions'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    simulation_id: Mapped[str] = mapped_column(String(100), index=True)
    situation: Mapped[str] = mapped_column(String(2000))
    selected_action: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float, default=.5)
    reasoning_factors: Mapped[list] = mapped_column(JSON, default=list)
    options: Mapped[list] = mapped_column(JSON, default=list)
    information_state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ActionModel(Base):
    __tablename__ = 'actions'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(100), index=True)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    action_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default='proposed')
    effects: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ActorPerceptionModel(Base):
    __tablename__ = 'actor_perceptions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(String(100), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    facts_json: Mapped[dict] = mapped_column(JSON, default=dict)

class EffectModel(Base):
    __tablename__ = 'effects'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(String(100), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(64))
    field: Mapped[str] = mapped_column(String(100))
    delta: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=1)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    mechanism: Mapped[str] = mapped_column(String(50), default='direct')

class ForecastModel(Base):
    __tablename__ = 'forecasts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(String(100), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    target: Mapped[str] = mapped_column(String(200))
    horizon: Mapped[int] = mapped_column(Integer)
    expected: Mapped[float] = mapped_column(Float)
    lower: Mapped[float] = mapped_column(Float)
    upper: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    drivers: Mapped[dict] = mapped_column(JSON, default=dict)

class IngestionQueueModel(Base):
    __tablename__ = 'ingestion_queue'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default='pending', index=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class WorldStateVersionModel(Base):
    __tablename__ = 'world_state_versions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(String(100), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    state_hash: Mapped[str] = mapped_column(String(128), index=True)
    parent_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dataset_version: Mapped[str] = mapped_column(String(100), default='live')
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('simulation_id', 'tick', name='uq_world_state_version'),)
