from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.session_grounding_store import get_session_grounding_store


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
    store = get_session_grounding_store()
    drawing_image_base64 = "aGVsbG8="
    child_context = {"child_name": "Luna"}

    response = client.post(
        f"/api/session/{session_id}/persona/derive",
        json={
            "drawing_image_base64": drawing_image_base64,
            "drawing_mime_type": "image/png",
            "child_context": child_context,
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
    assert payload["data"]["bootstrap_ready"] is True

    pending_drawing = store.get_pending_drawing(session_id)
    assert pending_drawing is not None
    assert pending_drawing.drawing_image_base64 == drawing_image_base64
    assert pending_drawing.drawing_mime_type == "image/png"
    assert pending_drawing.child_context == child_context
    assert store.get_bootstrap_context(session_id) is None

    persona = store.get_persona(session_id)
    assert persona is not None
    assert persona.voice_traits == ["playful", "friendly"]
    assert persona.personality_traits == ["curious", "kind"]
    assert "Luna" in persona.greeting_text


def test_persona_derivation_applies_fallback_when_model_times_out() -> None:
    session_id = _start_session()
    store = get_session_grounding_store()

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
    assert payload["data"]["bootstrap_ready"] is True

    persona = store.get_persona(session_id)
    assert persona is not None
    assert persona.voice_traits == ["gentle", "warm"]
    assert persona.personality_traits == ["calm", "supportive"]
