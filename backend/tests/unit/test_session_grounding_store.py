"""Tests for session_grounding_store — persona storage and retrieval."""
from __future__ import annotations

from app.services.session_grounding_store import SessionGroundingStore


def test_store_persona_and_retrieve() -> None:
    store = SessionGroundingStore()
    store.register_session("s1")
    store.store_persona(
        "s1",
        voice_traits=["playful", "friendly"],
        personality_traits=["curious", "kind"],
        greeting_text="Oi, sou seu amigo!",
    )

    persona = store.get_persona("s1")
    assert persona is not None
    assert persona.voice_traits == ["playful", "friendly"]
    assert persona.personality_traits == ["curious", "kind"]
    assert persona.greeting_text == "Oi, sou seu amigo!"


def test_get_persona_returns_none_for_unknown_session() -> None:
    store = SessionGroundingStore()
    assert store.get_persona("nonexistent") is None


def test_get_persona_returns_none_before_storage() -> None:
    store = SessionGroundingStore()
    store.register_session("s2")
    assert store.get_persona("s2") is None


def test_store_persona_auto_registers_session() -> None:
    store = SessionGroundingStore()
    store.store_persona(
        "auto-reg",
        voice_traits=["gentle"],
        personality_traits=["calm"],
        greeting_text="Hello",
    )
    assert store.has_session("auto-reg") is True
    assert store.get_persona("auto-reg") is not None
