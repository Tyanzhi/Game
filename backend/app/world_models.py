from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class CountryModel(Base):
    __tablename__ = "countries"

    id: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("actors.id"), unique=True)
    region: Mapped[str | None] = mapped_column(String(100))


class RelationshipModel(Base):
    __tablename__ = "relationships"

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
