"""Tests for GET /api/dashboard/insights/{session_id} — WS4 therapist endpoint."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services.clinical_session_store import get_clinical_session_store
from app.api.session import _session_grounding_store


@pytest.fixture(autouse=True)
def _clean_clinical_store():
    """Ensure a clean clinical store for each test."""
    store = get_clinical_session_store()
    store._sessions.clear()
    _session_grounding_store._sessions.clear()
    yield
    store._sessions.clear()
    _session_grounding_store._sessions.clear()


def test_insights_endpoint_returns_session_not_found_for_unknown_session() -> None:
    client = TestClient(app)
    response = client.get("/api/dashboard/insights/nonexistent-session")
    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "SESSION_NOT_FOUND"


def test_insights_endpoint_returns_empty_data_for_registered_session() -> None:
    store = get_clinical_session_store()
    store.register_session("s-empty")

    client = TestClient(app)
    response = client.get("/api/dashboard/insights/s-empty")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["session_id"] == "s-empty"
    assert body["data"]["alerts"] == []
    assert body["data"]["payloads"] == []
    assert body["data"]["summaries"] == []
    assert body["data"]["is_closed"] is False
    assert body["data"]["ended_at"] is None


def test_insights_endpoint_returns_stored_alerts_and_payloads() -> None:
    store = get_clinical_session_store()
    store.register_session("s-rich")
    store.add_alert("s-rich", {"primary_emotion": "fear", "risk_level": "high"})
    store.add_payload("s-rich", {"primary_emotion": "fear", "trigger": "dark room"})
    store.add_summary("s-rich", "Child expressed fear about darkness.")

    client = TestClient(app)
    response = client.get("/api/dashboard/insights/s-rich")
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["session_id"] == "s-rich"
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["primary_emotion"] == "fear"
    assert len(data["payloads"]) == 1
    assert data["payloads"][0]["trigger"] == "dark room"
    assert len(data["summaries"]) == 1
    assert "fear" in data["summaries"][0]


def test_insights_endpoint_multiple_alerts_accumulate() -> None:
    store = get_clinical_session_store()
    store.register_session("s-multi")
    store.add_alert("s-multi", {"emotion": "fear"})
    store.add_alert("s-multi", {"emotion": "anger"})
    store.add_alert("s-multi", {"emotion": "sadness"})

    client = TestClient(app)
    response = client.get("/api/dashboard/insights/s-multi")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["alerts"]) == 3


def test_insights_endpoint_returns_closed_state_from_grounding_store() -> None:
    client = TestClient(app)
    response = client.post("/api/session/start", json={"caregiver_consent": True})
    session_id = response.json()["data"]["session_id"]

    clinical_store = get_clinical_session_store()
    clinical_store.register_session(session_id)

    end_response = client.post(f"/api/session/{session_id}/end")
    ended_at = end_response.json()["data"]["ended_at"]

    insights_response = client.get(f"/api/dashboard/insights/{session_id}")
    assert insights_response.status_code == 200
    data = insights_response.json()["data"]
    assert data["is_closed"] is True
    assert data["ended_at"] == ended_at


# ---------------------------------------------------------------------------
# emotional_state_current — WS-FinalMile backend authority
# ---------------------------------------------------------------------------


def test_insights_endpoint_emotional_state_defaults_to_calm() -> None:
    store = get_clinical_session_store()
    store.register_session("s-emo-calm")

    client = TestClient(app)
    response = client.get("/api/dashboard/insights/s-emo-calm")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["emotional_state_current"] == "calm"


def test_insights_endpoint_includes_emotional_state_from_store() -> None:
    store = get_clinical_session_store()
    store.register_session("s-emo-happy")
    store.set_emotional_state("s-emo-happy", "joyful")

    client = TestClient(app)
    response = client.get("/api/dashboard/insights/s-emo-happy")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["emotional_state_current"] == "joyful"
