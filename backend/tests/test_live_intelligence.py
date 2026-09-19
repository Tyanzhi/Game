from datetime import datetime, timezone

from app.event_engine import RawEvent
from app.live_intelligence import classify_event_type, link_event_actors
from app.models import ActorModel


def test_live_event_classification_and_actor_linking():
    actors = [
        ActorModel(id="chn", name="China"),
        ActorModel(id="usa", name="United States"),
    ]
    event = RawEvent(
        source_id="gdelt",
        source_url="https://example.com/story",
        title="China faces major oil pipeline disruption after attack",
        description="Beijing officials report an energy disruption.",
        timestamp=datetime.now(timezone.utc),
        event_type="news_report",
        confidence=0.55,
    )

    linked = link_event_actors(event, actors)
    assert "chn" in linked.actor_ids
    assert linked.event_type in {"energy_disruption", "security_incident"}


def test_live_classifier_covers_core_crisis_types():
    assert classify_event_type("earthquake causes widespread disaster") == "natural_disaster"
    assert classify_event_type("inflation and recession deepen debt crisis") == "economic_crisis"
    assert classify_event_type("large protest triggers government crisis") == "internal_crisis"
    assert classify_event_type("ambassador recalled amid diplomatic dispute") == "diplomatic_crisis"
