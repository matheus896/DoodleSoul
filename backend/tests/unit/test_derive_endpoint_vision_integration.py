"""Tests for the derive_persona endpoint using the VisionPersonaDeriver integration.

These tests validate that the endpoint correctly delegates
to VisionPersonaDeriver when the module-level deriver is initialized,
and uses deterministic fallback when it's not.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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


def test_derive_endpoint_uses_vision_deriver_when_initialized() -> None:
    """Given a VisionPersonaDeriver has been initialized at module level,
    when persona derivation is called without force_timeout,
    then it delegates to the VisionPersonaDeriver and returns model-derived traits."""
    session_id = _start_session()

    vision_result = {
        "persona_source": "drawing_derived",
        "fallback_applied": False,
        "fallback_reason": None,
        "voice_traits": ["cheerful", "energetic"],
        "personality_traits": ["adventurous", "friendly"],
        "greeting_text": "Hi Luna, I am Drago from your drawing!",
    }

    mock_deriver = MagicMock()
    mock_deriver.derive = AsyncMock(return_value=vision_result)

    with patch("app.api.session._vision_deriver", mock_deriver):
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
    assert payload["data"]["persona_source"] == "drawing_derived"
    assert "cheerful" in payload["data"]["voice_traits"]
    assert payload["data"]["greeting_text"] == "Hi Luna, I am Drago from your drawing!"
    mock_deriver.derive.assert_awaited_once()


def test_derive_endpoint_falls_back_when_deriver_not_initialized() -> None:
    """Given no VisionPersonaDeriver has been initialized (default state in tests),
    when persona derivation is called,
    then it uses the deterministic fallback (original behavior)."""
    session_id = _start_session()

    # Explicitly ensure _vision_deriver is None (the default test state)
    with patch("app.api.session._vision_deriver", None):
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
    # Falls back to deterministic mock behavior
    assert payload["data"]["persona_source"] == "drawing_derived"
    assert payload["data"]["greeting_text"]


def test_derive_endpoint_force_timeout_always_uses_deterministic() -> None:
    """Given force_timeout is true and a real deriver is available,
    when persona derivation is called,
    then it still uses the deterministic fallback (force_timeout is a test hook)."""
    session_id = _start_session()

    mock_deriver = MagicMock()
    mock_deriver.derive = AsyncMock()

    with patch("app.api.session._vision_deriver", mock_deriver):
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
    assert payload["data"]["persona_source"] == "fallback"
    assert payload["data"]["fallback_applied"] is True
    # The real deriver should NOT have been called
    mock_deriver.derive.assert_not_awaited()
