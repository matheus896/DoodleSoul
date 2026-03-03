from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import pytest

from app.services.live_media_interceptor import (
    MediaToolCallInterceptingClient,
    MediaToolCallInterceptingStream,
    maybe_wrap_live_client_with_media_orchestrator,
)


class FakeBaseStream:
    def __init__(self, events: list[dict[str, Any] | bytes]) -> None:
        self._events = list(events)
        self.closed = False
        self.upstream_audio: list[bytes] = []
        self.upstream_text: list[str] = []

    async def send_realtime_audio(self, audio_chunk: bytes) -> None:
        self.upstream_audio.append(audio_chunk)

    async def send_text(self, text: str) -> None:
        self.upstream_text.append(text)

    async def _iter(self) -> AsyncIterator[dict[str, Any] | bytes]:
        for event in self._events:
            yield event
            await asyncio.sleep(0)

    def iter_events(self) -> AsyncIterator[dict[str, Any] | bytes]:
        return self._iter()

    async def close(self) -> None:
        self.closed = True


class FakeBaseClient:
    def __init__(self, stream: FakeBaseStream) -> None:
        self.stream = stream

    async def open_stream(self, session_id: str) -> FakeBaseStream:
        _ = session_id
        return self.stream


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def orchestrate_scene(
        self,
        *,
        scene_id: str,
        image_prompt: str,
        video_prompt: str,
        event_sink: Any,
    ) -> None:
        self.calls.append(
            {
                "scene_id": scene_id,
                "image_prompt": image_prompt,
                "video_prompt": video_prompt,
            }
        )
        await event_sink({"type": "drawing_in_progress", "scene_id": scene_id})
        await event_sink({"type": "media.image.created", "scene_id": scene_id, "url": "mock://img"})
        await event_sink({"type": "media.video.created", "scene_id": scene_id, "url": "mock://vid"})


async def _collect_events(stream: MediaToolCallInterceptingStream) -> list[dict[str, Any] | bytes]:
    events: list[dict[str, Any] | bytes] = []
    async for event in stream.iter_events():
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_interceptor_triggers_orchestrator_on_tool_call() -> None:
    base_stream = FakeBaseStream(
        events=[
            b"audio-1",
            {
                "type": "tool_call",
                "tool": "generate_image",
                "scene_id": "scene-1",
                "prompt": "blue robot in a park",
            },
            b"audio-2",
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    events = await _collect_events(stream)

    assert b"audio-1" in events
    assert b"audio-2" in events
    assert any(isinstance(e, dict) and e.get("type") == "tool_call" for e in events)
    assert any(isinstance(e, dict) and e.get("type") == "drawing_in_progress" for e in events)
    assert any(isinstance(e, dict) and e.get("type") == "media.image.created" for e in events)
    assert any(isinstance(e, dict) and e.get("type") == "media.video.created" for e in events)
    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["scene_id"] == "scene-1"


@pytest.mark.asyncio
async def test_interceptor_deduplicates_scene_tool_calls() -> None:
    base_stream = FakeBaseStream(
        events=[
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-a"},
            {"type": "tool_call", "tool": "generate_video", "scene_id": "scene-a"},
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    _ = await _collect_events(stream)

    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["scene_id"] == "scene-a"


@pytest.mark.asyncio
async def test_interceptor_passthrough_non_tool_events() -> None:
    event = {"type": "text", "text": "hello"}
    base_stream = FakeBaseStream(events=[event])
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    events = await _collect_events(stream)

    assert events == [event]
    assert orchestrator.calls == []


@pytest.mark.asyncio
async def test_intercepting_client_wraps_opened_stream() -> None:
    base_stream = FakeBaseStream(events=[])
    base_client = FakeBaseClient(stream=base_stream)
    orchestrator = FakeOrchestrator()

    client = MediaToolCallInterceptingClient(
        base_client=base_client,
        media_orchestrator=orchestrator,
    )

    stream = await client.open_stream(session_id="s1")
    assert isinstance(stream, MediaToolCallInterceptingStream)


def test_maybe_wrap_bypasses_mock_and_pilot_modes() -> None:
    base_client = object()
    orchestrator = FakeOrchestrator()

    same_mock = maybe_wrap_live_client_with_media_orchestrator(
        client=base_client,
        live_mode="mock",
        media_orchestrator=orchestrator,
    )
    same_pilot = maybe_wrap_live_client_with_media_orchestrator(
        client=base_client,
        live_mode="pilot",
        media_orchestrator=orchestrator,
    )

    assert same_mock is base_client
    assert same_pilot is base_client


def test_maybe_wrap_uses_injected_orchestrator_in_adk_mode() -> None:
    base_client = object()
    orchestrator = FakeOrchestrator()

    wrapped = maybe_wrap_live_client_with_media_orchestrator(
        client=base_client,
        live_mode="adk",
        media_orchestrator=orchestrator,
    )

    assert isinstance(wrapped, MediaToolCallInterceptingClient)
