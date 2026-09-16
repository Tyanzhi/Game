from datetime import datetime, timezone, timedelta

from app.event_engine import RawEvent, fingerprint, normalize


def raw(source: str, title: str, hours: int = 0) -> RawEvent:
    return RawEvent(
        source_id=source,
        source_url=f"https://example.test/{source}",
        title=title,
        description=title,
        timestamp=datetime(2026, 9, 16, 8, tzinfo=timezone.utc) + timedelta(hours=hours),
        event_type="diplomatic",
        confidence=0.6,
    )


def test_cross_source_story_is_deduplicated():
    events = normalize([raw("a", "Leaders hold diplomatic talks", 0), raw("b", "Leaders hold diplomatic talks", 2)])
    assert len(events) == 1
    assert events[0].source_count == 2
    assert events[0].status == "FACT"
    assert events[0].confidence > 0.6


def test_different_stories_remain_separate():
    events = normalize([raw("a", "Leaders hold diplomatic talks"), raw("b", "Central bank changes interest rate")])
    assert len(events) == 2


def test_fingerprint_is_stable():
    event = raw("a", "Same event")
    assert fingerprint(event) == fingerprint(event)
