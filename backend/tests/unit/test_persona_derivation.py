from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _start_session() -> str:
    response = client.post(
        "/api/session/start",
        json={"caregiver_consent": True},
    )
    assert response.status_code == 200
    return response.json()["data"]["session_id"]


def test_persona_derivation_returns_traits_for_valid_drawing() -> None:
    session_id = _start_session()

    response = client.post(
        f"/api/session/{session_id}/persona/derive",
        json={
            "drawing_image_base64": "aGVsbG8=",
            "drawing_mime_type": "image/png",
            "child_context": {"child_name": "Luna"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["session_id"] == session_id
    assert payload["data"]["persona_source"] == "drawing_derived"
    assert payload["data"]["fallback_applied"] is False
    assert payload["data"]["voice_traits"]
    assert payload["data"]["personality_traits"]
    assert payload["data"]["greeting_text"]


def test_persona_derivation_applies_fallback_when_model_times_out() -> None:
    session_id = _start_session()

    response = client.post(
        f"/api/session/{session_id}/persona/derive",
        json={
            "drawing_image_base64": "aGVsbG8=",
            "drawing_mime_type": "image/png",
            "force_timeout": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["session_id"] == session_id
    assert payload["data"]["persona_source"] == "fallback"
    assert payload["data"]["fallback_applied"] is True
    assert payload["data"]["fallback_reason"] == "derivation_timeout"
    assert payload["data"]["voice_traits"]
    assert payload["data"]["personality_traits"]
    assert payload["data"]["greeting_text"]
