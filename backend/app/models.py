from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActorModel(Base):
    __tablename__ = "actors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), default="state", nullable=False)
    stability: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    economic_capacity: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    diplomatic_capacity: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    security_capacity: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    domestic_pressure: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CountryModel(Base):
    __tablename__ = "countries"

    id: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"), unique=True)
    region: Mapped[str | None] = mapped_column(String(100))


class RelationshipModel(Base):
    __tablename__ = "relationships"
    __table_args__ = (UniqueConstraint("source_actor_id", "target_actor_id", name="uq_relationship_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"), nullable=False)
    target_actor_id: Mapped[str] = mapped_column(ForeignKey("actors.id"), nullable=False)
    diplomatic: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    economic: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    military: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    trade: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    energy: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    technology: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    political: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    information: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="FACT", nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class EventSourceModel(Base):
    __tablename__ = "event_sources"
    __table_args__ = (UniqueConstraint("event_id", "source_id", name="uq_event_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class SimulationRunModel(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), default="live", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    query: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    events_ingested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    events_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    events_deduplicated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SimulationTickModel(Base):
    __tablename__ = "simulation_ticks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    event_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    state_changes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WorldSnapshotModel(Base):
    __tablename__ = "world_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)
    simulation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
