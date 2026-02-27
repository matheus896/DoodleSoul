from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncIterator

from app.config.env_loader import load_env_once
from app.services.gemini_client import GeminiLiveClient


class MockGeminiLiveStream:
    def __init__(self) -> None:
        self._events: asyncio.Queue[dict[str, Any] | bytes | None] = asyncio.Queue()
        self._closed = False

    async def send_realtime_audio(self, audio_chunk: bytes) -> None:
        if self._closed:
            return
        await self._events.put(audio_chunk)

    async def send_text(self, text: str) -> None:
        if self._closed:
            return
        await self._events.put({"text": f"echo:{text}"})

    async def _iter(self) -> AsyncIterator[dict[str, Any] | bytes]:
        while True:
            event = await self._events.get()
            if event is None:
                break
            yield event

    def iter_events(self) -> AsyncIterator[dict[str, Any] | bytes]:
        return self._iter()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._events.put(None)


async def _mock_stream_factory(*, model: str, session_id: str):
    _ = model, session_id
    return MockGeminiLiveStream()


def get_live_model() -> str:
    load_env_once()
    return os.getenv("DEMO_AGENT_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")


def build_live_client() -> GeminiLiveClient:
    load_env_once()
    live_mode = os.getenv("ANIMISM_LIVE_MODE", "adk").lower()
    if live_mode == "mock":
        return GeminiLiveClient(model=get_live_model(), stream_factory=_mock_stream_factory)
    return GeminiLiveClient(model=get_live_model())
