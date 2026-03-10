"""Tests for VisionPersonaDeriver — the real Gemini Vision adapter for persona derivation.

TDD RED phase: These tests are written BEFORE the production module exists.
They validate the adapter boundary: success, timeout, and API error paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_IMAGE_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAoMBgQfM9tYAAAAASUVORK5CYII="
VALID_MIME_TYPE = "image/png"


def _build_mock_genai_response(text: str) -> MagicMock:
    """Build a mock genai response object that has .text returning JSON."""
    response = MagicMock()
    response.text = text
    return response


# ---------------------------------------------------------------------------
# Test: successful vision derivation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_deriver_returns_structured_traits_on_success() -> None:
    """Given a valid drawing image and a responsive Gemini Vision API,
    when the deriver is called,
    then it returns persona traits parsed from the model response."""
    from app.services.vision_persona_deriver import VisionPersonaDeriver

    vision_json = (
        '{"voice_traits": ["cheerful", "energetic"],'
        ' "personality_traits": ["adventurous", "friendly"],'
        ' "greeting_text": "Oi Luna, eu sou o Drago do seu desenho!"}'
    )
    mock_response = _build_mock_genai_response(vision_json)

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    deriver = VisionPersonaDeriver(client=mock_client, model="gemini-3.1-flash-lite-preview")

    result = await deriver.derive(
        drawing_image_base64=VALID_IMAGE_BASE64,
        drawing_mime_type=VALID_MIME_TYPE,
        child_context={"child_name": "Luna"},
    )

    assert result["persona_source"] == "drawing_derived"
    assert result["fallback_applied"] is False
    assert result["fallback_reason"] is None
    assert "cheerful" in result["voice_traits"]
    assert "adventurous" in result["personality_traits"]
    assert "Luna" in result["greeting_text"] or "Drago" in result["greeting_text"]

    # Verify the API was actually called with image content
    mock_client.aio.models.generate_content.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: timeout fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_deriver_returns_fallback_on_timeout() -> None:
    """Given a Gemini Vision API that times out,
    when the deriver is called,
    then it returns a graceful fallback payload without crashing."""
    from app.services.vision_persona_deriver import VisionPersonaDeriver

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=TimeoutError("Vision API timed out")
    )

    deriver = VisionPersonaDeriver(client=mock_client, model="gemini-3.1-flash-lite-preview")

    result = await deriver.derive(
        drawing_image_base64=VALID_IMAGE_BASE64,
        drawing_mime_type=VALID_MIME_TYPE,
    )

    assert result["persona_source"] == "fallback"
    assert result["fallback_applied"] is True
    assert result["fallback_reason"] == "derivation_timeout"
    assert len(result["voice_traits"]) > 0
    assert len(result["personality_traits"]) > 0
    assert len(result["greeting_text"]) > 0


# ---------------------------------------------------------------------------
# Test: generic API error fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_deriver_returns_fallback_on_api_error() -> None:
    """Given a Gemini Vision API that returns a server error,
    when the deriver is called,
    then it returns a graceful fallback payload with error reason."""
    from app.services.vision_persona_deriver import VisionPersonaDeriver

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=Exception("500 Internal Server Error")
    )

    deriver = VisionPersonaDeriver(client=mock_client, model="gemini-3.1-flash-lite-preview")

    result = await deriver.derive(
        drawing_image_base64=VALID_IMAGE_BASE64,
        drawing_mime_type=VALID_MIME_TYPE,
    )

    assert result["persona_source"] == "fallback"
    assert result["fallback_applied"] is True
    assert result["fallback_reason"] == "derivation_error"
    assert len(result["voice_traits"]) > 0
    assert len(result["personality_traits"]) > 0
    assert len(result["greeting_text"]) > 0


# ---------------------------------------------------------------------------
# Test: malformed model response fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_deriver_returns_fallback_on_malformed_response() -> None:
    """Given a Gemini Vision API that returns non-JSON or missing fields,
    when the deriver is called,
    then it returns a fallback instead of crashing."""
    from app.services.vision_persona_deriver import VisionPersonaDeriver

    mock_response = _build_mock_genai_response("this is not valid json {{{")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    deriver = VisionPersonaDeriver(client=mock_client, model="gemini-3.1-flash-lite-preview")

    result = await deriver.derive(
        drawing_image_base64=VALID_IMAGE_BASE64,
        drawing_mime_type=VALID_MIME_TYPE,
    )

    assert result["persona_source"] == "fallback"
    assert result["fallback_applied"] is True
    assert result["fallback_reason"] == "derivation_parse_error"
    assert len(result["voice_traits"]) > 0
