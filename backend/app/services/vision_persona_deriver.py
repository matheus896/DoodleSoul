"""VisionPersonaDeriver — calls Gemini Vision to derive persona traits from a child's drawing.

This module encapsulates the adapter boundary between the persona derivation
endpoint and the Gemini Vision API.  On success it parses structured traits from
the model response.  On any error (timeout, API error, malformed output) it
returns a deterministic fallback payload so the startup flow never crashes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

VISION_TIMEOUT_SECONDS = 10.0

PERSONA_PROMPT = """\
You are a creative character designer for a children's therapy app.

Analyze ALL visual elements in the child's drawing attached as an image. Look carefully at colours, shapes, ALL characters, background objects, and the environment.
Based on everything you see, derive a unique persona for an AI companion.

Return ONLY a valid JSON object with exactly these fields:
{
  "drawing_summary": "A detailed 1-2 sentence description listing ALL key items, characters, and background elements found in the drawing.",
  "voice_traits": ["trait1", "trait2"],
  "personality_traits": ["trait1", "trait2"],
  "greeting_text": "A short, warm greeting in English (max 2 sentences). You MUST explicitly mention multiple specific details from the drawing to show the child you see everything they drew. If a child_name is provided, include it."
}

Rules:
- voice_traits: 2-4 descriptive adjectives for the character's voice (e.g. "cheerful", "gentle", "energetic").
- personality_traits: 2-4 descriptive adjectives for the character's personality (e.g. "adventurous", "kind", "curious").
- greeting_text: A warm greeting in English referencing multiple specific items from the drawing. If the child's name is provided below, include it.
- drawing_summary: Must contain all elements visible in the drawing.
- Do NOT wrap the JSON in markdown code fences.
- Do NOT include any text outside the JSON object.
"""


class PersonaPayload(TypedDict):
    persona_source: str
    fallback_applied: bool
    fallback_reason: str | None
    drawing_summary: str
    voice_traits: list[str]
    personality_traits: list[str]
    greeting_text: str


def _fallback_payload(reason: str) -> PersonaPayload:
    """Return a safe deterministic fallback persona."""
    return PersonaPayload(
        persona_source="fallback",
        fallback_applied=True,
        fallback_reason=reason,
        drawing_summary="A child's imaginative drawing.",
        voice_traits=["gentle", "warm"],
        personality_traits=["calm", "supportive"],
        greeting_text="Hi, let's play together!",
    )


def _parse_model_response(text: str) -> dict[str, Any]:
    """Parse the model text response as JSON, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove markdown code fences
        lines = cleaned.splitlines()
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    return json.loads(cleaned)


class VisionPersonaDeriver:
    """Adapter that calls Gemini Vision to derive persona traits from a drawing image."""

    def __init__(self, *, client: Any, model: str = "gemini-3.1-flash-lite-preview") -> None:
        self._client = client
        self._model = model

    async def derive(
        self,
        *,
        drawing_image_base64: str,
        drawing_mime_type: str,
        child_context: dict[str, str] | None = None,
    ) -> PersonaPayload:
        """Derive persona traits from the given drawing image.

        Returns PersonaPayload with ``persona_source="drawing_derived"`` on
        success, or ``persona_source="fallback"`` on any failure.
        """
        try:
            result = await self._call_vision_api(
                drawing_image_base64=drawing_image_base64,
                drawing_mime_type=drawing_mime_type,
                child_context=child_context,
            )
            return result
        except TimeoutError:
            logger.warning("Vision persona derivation timed out")
            return _fallback_payload("derivation_timeout")
        except Exception:
            logger.exception("Vision persona derivation failed")
            return _fallback_payload("derivation_error")

    async def _call_vision_api(
        self,
        *,
        drawing_image_base64: str,
        drawing_mime_type: str,
        child_context: dict[str, str] | None = None,
    ) -> PersonaPayload:
        """Internal: call the Gemini Vision API with the drawing and parse the response."""
        from google.genai import types

        prompt_text = PERSONA_PROMPT
        if child_context and child_context.get("child_name"):
            prompt_text += f"\nChild's name: {child_context['child_name']}"

        img_b64 = drawing_image_base64
        if img_b64.startswith("data:"):
            img_b64 = img_b64.split(",", 1)[-1]

        image_part = types.Part.from_bytes(
            data=__import__("base64").b64decode(img_b64),
            mime_type=drawing_mime_type,
        )
        text_part = types.Part.from_text(text=prompt_text)

        contents = [types.Content(role="user", parts=[image_part, text_part])]

        response = await asyncio.wait_for(
            self._client.aio.models.generate_content(
                model=self._model,
                contents=contents,
            ),
            timeout=VISION_TIMEOUT_SECONDS,
        )

        try:
            parsed = _parse_model_response(response.text)
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Failed to parse vision response as JSON: %s", response.text[:200])
            return _fallback_payload("derivation_parse_error")

        # Validate required fields
        drawing_summary = parsed.get("drawing_summary")
        voice_traits = parsed.get("voice_traits")
        personality_traits = parsed.get("personality_traits")
        greeting_text = parsed.get("greeting_text")

        if (
            not isinstance(drawing_summary, str)
            or not isinstance(voice_traits, list)
            or not isinstance(personality_traits, list)
            or not isinstance(greeting_text, str)
            or not voice_traits
            or not personality_traits
            or not greeting_text
        ):
            logger.warning("Vision response missing required fields: %s", parsed)
            return _fallback_payload("derivation_parse_error")

        return PersonaPayload(
            persona_source="drawing_derived",
            fallback_applied=False,
            fallback_reason=None,
            drawing_summary=drawing_summary,
            voice_traits=voice_traits,
            personality_traits=personality_traits,
            greeting_text=greeting_text,
        )
