from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def test_start_session_returns_ephemeral_session_id_when_consent_is_confirmed() -> None:
    response = client.post(
        "/api/session/start",
        json={"caregiver_consent": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["consent_captured"] is True
    assert _is_uuid(payload["data"]["session_id"])


def test_start_session_returns_distinct_session_ids_for_each_call() -> None:
    first_response = client.post(
        "/api/session/start",
        json={"caregiver_consent": True},
    )
    second_response = client.post(
        "/api/session/start",
        json={"caregiver_consent": True},
    )

    first_session_id = first_response.json()["data"]["session_id"]
    second_session_id = second_response.json()["data"]["session_id"]

    assert first_session_id != second_session_id


def test_start_session_rejects_when_consent_is_missing_or_false() -> None:
    false_response = client.post(
        "/api/session/start",
        json={"caregiver_consent": False},
    )
    missing_response = client.post("/api/session/start", json={})

    for response in (false_response, missing_response):
        assert response.status_code == 400
        payload = response.json()
        assert payload["status"] == "error"
        assert payload["error"]["code"] == "consent_required"
