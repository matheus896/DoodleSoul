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


class StartSessionRequest(BaseModel):
    caregiver_consent: bool | None = Field(default=None)


class StartSessionData(BaseModel):
    session_id: str
    consent_captured: bool
    consent_captured_at: str


_consent_store = InMemoryConsentStore()


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
    data = StartSessionData(
        session_id=session_id,
        consent_captured=True,
        consent_captured_at=consent_record.consent_captured_at,
    )
    return {
        "status": "ok",
        "data": data.model_dump(),
    }
