from __future__ import annotations

from app.services.gemini_client import GeminiLiveClient
from app.services.live_client_factory import build_live_client, get_live_model


def test_get_live_model_default(monkeypatch) -> None:
    monkeypatch.delenv("DEMO_AGENT_MODEL", raising=False)
    assert get_live_model() == "gemini-2.5-flash-native-audio-preview-12-2025"


def test_build_live_client_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("ANIMISM_LIVE_MODE", "mock")
    client = build_live_client()
    assert isinstance(client, GeminiLiveClient)
