from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse


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


def _derive_persona_payload(
    session_id: str,
    request: PersonaDerivationRequest,
) -> PersonaDerivationData:
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

    data = _derive_persona_payload(session_id=session_id, request=request)
    return {
        "status": "ok",
        "data": data.model_dump(),
    }
