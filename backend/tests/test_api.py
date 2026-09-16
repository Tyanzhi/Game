from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_world_state():
    response = client.get("/api/world/state")
    assert response.status_code == 200
    body = response.json()
    assert "actors" in body
    assert "usa" in body["actors"]


def test_event_changes_state():
    response = client.post(
        "/api/events",
        json={
            "event_id": "evt-test",
            "event_type": "economic",
            "actor_ids": ["usa"],
            "impact": {"stability": -0.1},
            "confidence": 0.9,
            "status": "FACT",
        },
    )
    assert response.status_code == 200
