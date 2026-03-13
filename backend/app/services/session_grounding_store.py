from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


class BootstrapContextDict(TypedDict):
    character_name: str
    drawing_summary: str
    visual_traits: list[str]
    voice_traits: list[str]
    personality_traits: list[str]
    story_seed: str
    first_turn_guidance: str
    child_context_summary: str
    follow_up_question: str
    confidence_notes: str


@dataclass(slots=True)
class PersonaContext:
    voice_traits: list[str]
    personality_traits: list[str]
    greeting_text: str


@dataclass(slots=True)
class PendingDrawing:
    drawing_image_base64: str
    drawing_mime_type: str
    child_context: dict[str, str] | None = None


@dataclass(slots=True)
class SessionGroundingState:
    pending_drawing: PendingDrawing | None = None
    bootstrap_context: BootstrapContextDict | None = None
    persona_context: PersonaContext | None = None
    is_closed: bool = False
    ended_at: str | None = None


class SessionGroundingStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionGroundingState] = {}

    def register_session(self, session_id: str) -> None:
        self._sessions.setdefault(session_id, SessionGroundingState())

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def is_closed(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        return state.is_closed

    def get_ended_at(self, session_id: str) -> str | None:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return state.ended_at

    def mark_closed(self, session_id: str, ended_at: str | None = None) -> str | None:
        self.register_session(session_id)
        state = self._sessions[session_id]
        state.is_closed = True
        if state.ended_at is None and ended_at is not None:
            state.ended_at = ended_at
        return state.ended_at

    def store_pending_drawing(
        self,
        session_id: str,
        *,
        drawing_image_base64: str,
        drawing_mime_type: str,
        child_context: dict[str, str] | None = None,
    ) -> None:
        self.register_session(session_id)
        self._sessions[session_id].pending_drawing = PendingDrawing(
            drawing_image_base64=drawing_image_base64,
            drawing_mime_type=drawing_mime_type,
            child_context=dict(child_context or {}),
        )

    def get_pending_drawing(self, session_id: str) -> PendingDrawing | None:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return state.pending_drawing

    def store_bootstrap_context(
        self,
        session_id: str,
        bootstrap_context: BootstrapContextDict | dict[str, object],
    ) -> None:
        self.register_session(session_id)
        self._sessions[session_id].bootstrap_context = BootstrapContextDict(
            character_name=str(bootstrap_context.get("character_name", "")),
            drawing_summary=str(bootstrap_context.get("drawing_summary", "")),
            visual_traits=[str(value) for value in bootstrap_context.get("visual_traits", [])],
            voice_traits=[str(value) for value in bootstrap_context.get("voice_traits", [])],
            personality_traits=[str(value) for value in bootstrap_context.get("personality_traits", [])],
            story_seed=str(bootstrap_context.get("story_seed", "")),
            first_turn_guidance=str(bootstrap_context.get("first_turn_guidance", "")),
            child_context_summary=str(bootstrap_context.get("child_context_summary", "")),
            follow_up_question=str(bootstrap_context.get("follow_up_question", "")),
            confidence_notes=str(bootstrap_context.get("confidence_notes", "")),
        )

    def get_bootstrap_context(self, session_id: str) -> BootstrapContextDict | None:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return state.bootstrap_context

    def store_persona(
        self,
        session_id: str,
        *,
        voice_traits: list[str],
        personality_traits: list[str],
        greeting_text: str,
    ) -> None:
        self.register_session(session_id)
        self._sessions[session_id].persona_context = PersonaContext(
            voice_traits=list(voice_traits),
            personality_traits=list(personality_traits),
            greeting_text=str(greeting_text),
        )

    def get_persona(self, session_id: str) -> PersonaContext | None:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return state.persona_context

    def clear_pending_drawing(self, session_id: str) -> None:
        state = self._sessions.get(session_id)
        if state is None:
            return
        state.pending_drawing = None


_SESSION_GROUNDING_STORE = SessionGroundingStore()


def get_session_grounding_store() -> SessionGroundingStore:
    return _SESSION_GROUNDING_STORE
