from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from app.services.vision_persona_deriver import VisionPersonaDeriver

logger = logging.getLogger(__name__)


router = APIRouter()


@dataclass(slots=True)
class ConsentRecord:
    session_id: str
    consent_captured_at: str


class InMemoryConsentStore:
    def __init__(self) -> None:
        self._records: list[ConsentRecord] = []

    def add(self, session_id: str) -> ConsentRecord:
        record = ConsentRecord(
            session_id=session_id,
            consent_captured_at=datetime.now(UTC).isoformat(),
        )
        self._records.append(record)
        return record


class InMemorySessionRegistry:
    def __init__(self) -> None:
        self._active_sessions: set[str] = set()

    def add(self, session_id: str) -> None:
        self._active_sessions.add(session_id)

    def has(self, session_id: str) -> bool:
        return session_id in self._active_sessions


class StartSessionRequest(BaseModel):
    caregiver_consent: bool | None = Field(default=None)


class StartSessionData(BaseModel):
    session_id: str
    consent_captured: bool
    consent_captured_at: str


class PersonaDerivationRequest(BaseModel):
    drawing_image_base64: str = Field(min_length=1)
    drawing_mime_type: str = Field(min_length=1)
    child_context: dict[str, str] | None = Field(default=None)
    force_timeout: bool = Field(default=False)


class PersonaDerivationData(BaseModel):
    session_id: str
    persona_source: str
    fallback_applied: bool
    fallback_reason: str | None
    voice_traits: list[str]
    personality_traits: list[str]
    greeting_text: str


_consent_store = InMemoryConsentStore()
_session_registry = InMemorySessionRegistry()

# Module-level vision deriver — None by default (deterministic fallback).
# Only set when init_vision_deriver() is called explicitly (e.g. at app startup).
_vision_deriver: VisionPersonaDeriver | None = None


def init_vision_deriver() -> None:
    """Initialize the vision deriver from GOOGLE_API_KEY if available.

    Call this at application startup to enable real Gemini Vision derivation.
    If not called (e.g. in unit tests), the endpoint uses deterministic fallback.
    """
    global _vision_deriver  # noqa: PLW0603
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.info("GOOGLE_API_KEY not set — persona derivation uses deterministic fallback")
        return
    try:
        from google import genai  # noqa: WPS433

        client = genai.Client(api_key=api_key)
        _vision_deriver = VisionPersonaDeriver(client=client)
        logger.info("VisionPersonaDeriver initialized with Gemini Vision API")
    except Exception:
        logger.warning("Failed to create VisionPersonaDeriver, using deterministic fallback")


def _get_vision_deriver() -> VisionPersonaDeriver | None:
    """Return the current vision deriver instance (None if not initialized)."""
    return _vision_deriver


def _deterministic_fallback_payload(
    session_id: str,
    request: PersonaDerivationRequest,
) -> PersonaDerivationData:
    """Original deterministic derivation — used when no vision API is available."""
    if request.force_timeout:
        return PersonaDerivationData(
            session_id=session_id,
            persona_source="fallback",
            fallback_applied=True,
            fallback_reason="derivation_timeout",
            voice_traits=["gentle", "warm"],
            personality_traits=["calm", "supportive"],
            greeting_text="Oi, vamos brincar juntos!",
        )

    child_name = None
    if request.child_context:
        child_name = request.child_context.get("child_name")
    name_fragment = f" {child_name}" if child_name else ""
    return PersonaDerivationData(
        session_id=session_id,
        persona_source="drawing_derived",
        fallback_applied=False,
        fallback_reason=None,
        voice_traits=["playful", "friendly"],
        personality_traits=["curious", "kind"],
        greeting_text=f"Oi{name_fragment}, sou seu amigo do desenho!",
    )


async def _derive_persona_payload(
    session_id: str,
    request: PersonaDerivationRequest,
    deriver: VisionPersonaDeriver | None = None,
) -> PersonaDerivationData:
    """Derive persona with real Vision API or deterministic fallback."""
    # force_timeout always uses deterministic fallback (test hook)
    if request.force_timeout:
        return _deterministic_fallback_payload(session_id, request)

    # If a real deriver is available, try it
    if deriver is not None:
        vision_result = await deriver.derive(
            drawing_image_base64=request.drawing_image_base64,
            drawing_mime_type=request.drawing_mime_type,
            child_context=request.child_context,
        )
        return PersonaDerivationData(
            session_id=session_id,
            **vision_result,
        )

    # No deriver available — use deterministic fallback
    return _deterministic_fallback_payload(session_id, request)


@router.post("/api/session/start")
async def start_session(request: StartSessionRequest):
    if request.caregiver_consent is not True:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "error": {
                    "code": "consent_required",
                    "message": "Confirme o consentimento do cuidador para iniciar a sessao.",
                },
            },
        )

    session_id = str(uuid4())
    consent_record = _consent_store.add(session_id)
    _session_registry.add(session_id)
    data = StartSessionData(
        session_id=session_id,
        consent_captured=True,
        consent_captured_at=consent_record.consent_captured_at,
    )
    return {
        "status": "ok",
        "data": data.model_dump(),
    }


@router.post("/api/session/{session_id}/persona/derive")
async def derive_persona(session_id: str, request: PersonaDerivationRequest):
    if not _session_registry.has(session_id):
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "error": {
                    "code": "session_not_found",
                    "message": "Sessao nao encontrada para derivacao de persona.",
                },
            },
        )

    deriver = _get_vision_deriver()
    data = await _derive_persona_payload(
        session_id=session_id,
        request=request,
        deriver=deriver,
    )
    return {
        "status": "ok",
        "data": data.model_dump(),
    }
