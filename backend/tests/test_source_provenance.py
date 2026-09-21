from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.event_engine import RawEvent, normalize
from app.event_store import persist_events
from app.models import Base, EventSourceModel


def raw(source_id, domain, url, confidence=0.55, quality=0.62):
    return RawEvent(
        source_id=source_id,
        source_url=url,
        title="Shared event headline",
        description="Shared event headline",
        timestamp=datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
        event_type="security_incident",
        confidence=confidence,
        source_quality=quality,
        raw={"domain": domain, "provider": "test"},
    )


def test_independent_origins_raise_confidence_and_fact_status():
    result = normalize([
        raw("gdelt:a.test", "a.test", "https://a.test/story"),
        raw("gdelt:b.test", "b.test", "https://b.test/story"),
    ])
    assert len(result) == 1
    event = result[0]
    assert event.status == "FACT"
    assert event.confidence > 0.55
    assert event.metadata["independent_source_count"] == 2
    assert event.metadata["source_quality_mean"] == pytest.approx(0.62)
    assert len(event.metadata["source_records"]) == 2


def test_same_origin_does_not_fake_independent_corroboration():
    result = normalize([
        raw("gdelt:a.test", "a.test", "https://a.test/story-1"),
        raw("gdelt:a.test", "a.test", "https://a.test/story-2"),
    ])
    event = result[0]
    assert event.metadata["independent_source_count"] == 1
    assert event.status == "CLAIM"


@pytest.mark.asyncio
async def test_event_store_keeps_each_provenance_url():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        event = normalize([
            raw("gdelt:a.test", "a.test", "https://a.test/story"),
            raw("gdelt:b.test", "b.test", "https://b.test/story"),
        ])[0]
        new_count, duplicate_count = await persist_events(session, [event])
        await session.commit()

        assert new_count == 1
        assert duplicate_count == 0
        rows = (
            await session.execute(
                select(EventSourceModel)
                .where(EventSourceModel.event_id == event.event_id)
                .order_by(EventSourceModel.source_id)
            )
        ).scalars().all()
        assert [(row.source_id, row.source_url) for row in rows] == [
            ("gdelt:a.test", "https://a.test/story"),
            ("gdelt:b.test", "https://b.test/story"),
        ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_corroboration_accumulates_across_ingestion_cycles():
    from app.models import EventModel

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        first = normalize([
            raw("gdelt:a.test", "a.test", "https://a.test/story"),
        ])[0]
        await persist_events(session, [first])
        await session.commit()

        stored = await session.get(EventModel, first.event_id)
        first_confidence = stored.confidence
        assert stored.source_count == 1
        assert stored.status == "CLAIM"

        second = normalize([
            raw("gdelt:b.test", "b.test", "https://b.test/story"),
        ])[0]
        assert second.event_id == first.event_id
        new_count, duplicate_count = await persist_events(session, [second])
        await session.commit()

        stored = await session.get(EventModel, first.event_id)
        assert new_count == 0
        assert duplicate_count == 1
        assert stored.source_count == 2
        assert stored.status == "FACT"
        assert stored.confidence > first_confidence
        assert stored.metadata_json["independent_source_count"] == 2

        rows = (
            await session.execute(
                select(EventSourceModel)
                .where(EventSourceModel.event_id == first.event_id)
            )
        ).scalars().all()
        assert {(row.source_id, row.source_url) for row in rows} == {
            ("gdelt:a.test", "https://a.test/story"),
            ("gdelt:b.test", "https://b.test/story"),
        }

    await engine.dispose()
