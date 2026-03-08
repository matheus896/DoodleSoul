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
        self.image_calls: list[dict[str, Any]] = []
        self.video_calls: list[dict[str, Any]] = []

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

    async def generate_image_only(
        self,
        *,
        scene_id: str,
        image_prompt: str,
        event_sink: Any,
    ) -> None:
        self.image_calls.append({"scene_id": scene_id, "image_prompt": image_prompt})
        await event_sink({"type": "drawing_in_progress", "scene_id": scene_id})
        await event_sink({"type": "media.image.created", "scene_id": scene_id, "url": "mock://img"})

    async def generate_video_only(
        self,
        *,
        scene_id: str,
        video_prompt: str,
        event_sink: Any,
        imagen_image: Any | None = None,
    ) -> None:
        self.video_calls.append(
            {"scene_id": scene_id, "video_prompt": video_prompt, "imagen_image": imagen_image}
        )
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
    assert not any(isinstance(e, dict) and e.get("type") == "media.video.created" for e in events)
    assert len(orchestrator.image_calls) == 1
    assert orchestrator.image_calls[0]["scene_id"] == "scene-1"
    assert orchestrator.calls == []


@pytest.mark.asyncio
async def test_interceptor_deduplicates_scene_tool_calls() -> None:
    base_stream = FakeBaseStream(
        events=[
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-a"},
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-a"},
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    _ = await _collect_events(stream)

    assert len(orchestrator.image_calls) == 1
    assert orchestrator.image_calls[0]["scene_id"] == "scene-a"


@pytest.mark.asyncio
async def test_interceptor_blocks_second_scene_after_first_generation() -> None:
    base_stream = FakeBaseStream(
        events=[
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-a"},
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-b"},
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    _ = await _collect_events(stream)

    assert len(orchestrator.image_calls) == 1
    assert orchestrator.image_calls[0]["scene_id"] == "scene-a"


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


# ---------------------------------------------------------------------------
# Debug toggle tests (Epic 3 Observability)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debug_logs_tool_call_recognized_when_enabled(monkeypatch, caplog) -> None:
    """When ANIMISM_DEBUG_MEDIA=1, a valid tool_call logs 'tool_call_recognized'."""
    monkeypatch.setenv("ANIMISM_DEBUG_MEDIA", "1")

    base_stream = FakeBaseStream(
        events=[
            {
                "type": "tool_call",
                "tool": "generate_image",
                "scene_id": "scene-dbg",
                "prompt": "a sunny park",
            }
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    with caplog.at_level("INFO", logger="app.services.debug_tracer"):
        await _collect_events(stream)

    assert any(
        "tool_call_recognized" in record.message and "scene-dbg" in record.message
        for record in caplog.records
    ), f"Expected 'tool_call_recognized' in logs. Got: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_debug_logs_media_awareness_sent_when_enabled(monkeypatch, caplog) -> None:
    """When debug on, successful model awareness injection is logged once per media event."""
    monkeypatch.setenv("ANIMISM_DEBUG_MEDIA", "1")

    base_stream = FakeBaseStream(
        events=[
            {
                "type": "tool_call",
                "tool": "generate_image",
                "scene_id": "scene-aware",
                "prompt": "a calm blue robot",
            }
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    with caplog.at_level("INFO", logger="app.services.debug_tracer"):
        await _collect_events(stream)

    assert any(
        "media_awareness_sent" in record.message
        and "scene-aware" in record.message
        and "media.image.created" in record.message
        for record in caplog.records
    ), f"Expected 'media_awareness_sent' in logs. Got: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_debug_logs_tool_call_blocked_by_session_lock_when_enabled(monkeypatch, caplog) -> None:
    """When ANIMISM_DEBUG_MEDIA=1, a second tool_call logs 'tool_call_blocked_session_lock'."""
    monkeypatch.setenv("ANIMISM_DEBUG_MEDIA", "1")

    base_stream = FakeBaseStream(
        events=[
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-dup"},
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-dup"},
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    with caplog.at_level("INFO", logger="app.services.debug_tracer"):
        await _collect_events(stream)

    assert any(
        "tool_call_blocked_session_lock" in record.message and "scene-dup" in record.message
        for record in caplog.records
    ), f"Expected 'tool_call_blocked_session_lock' in logs. Got: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_debug_logs_unrecognized_tool_like_payload_when_enabled(monkeypatch, caplog) -> None:
    """When debug on, a dict with type=tool_call but unknown tool logs 'tool_call_unrecognized'."""
    monkeypatch.setenv("ANIMISM_DEBUG_MEDIA", "1")

    base_stream = FakeBaseStream(
        events=[
            {
                "type": "tool_call",
                "tool": "unknown_tool",  # not in _MEDIA_TOOLS
                "scene_id": "scene-x",
            }
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    with caplog.at_level("INFO", logger="app.services.debug_tracer"):
        await _collect_events(stream)

    assert any(
        "tool_call_unrecognized" in record.message
        for record in caplog.records
    ), f"Expected 'tool_call_unrecognized'. Got: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_debug_silent_when_disabled(monkeypatch, caplog) -> None:
    """When ANIMISM_DEBUG_MEDIA is not set, no [ANIMISM_DEBUG] logs are emitted."""
    monkeypatch.delenv("ANIMISM_DEBUG_MEDIA", raising=False)

    base_stream = FakeBaseStream(
        events=[
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-q"},
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    with caplog.at_level("INFO", logger="app.services.debug_tracer"):
        await _collect_events(stream)

    assert not any(
        "[ANIMISM_DEBUG]" in record.message
        for record in caplog.records
    ), "Expected no debug logs when toggle is off"


def test_debug_logs_bypass_decision_in_mock_mode(monkeypatch, caplog) -> None:
    """When debug on, bypassing interceptor for mock mode is logged."""
    monkeypatch.setenv("ANIMISM_DEBUG_MEDIA", "1")

    base_client = object()
    orchestrator = FakeOrchestrator()

    with caplog.at_level("INFO", logger="app.services.debug_tracer"):
        maybe_wrap_live_client_with_media_orchestrator(
            client=base_client,
            live_mode="mock",
            media_orchestrator=orchestrator,
        )

    assert any(
        "interceptor_bypassed" in record.message and "mock" in record.message
        for record in caplog.records
    ), f"Expected 'interceptor_bypassed' for mock mode. Got: {[r.message for r in caplog.records]}"


def test_debug_logs_interceptor_active_in_adk_mode(monkeypatch, caplog) -> None:
    """When debug on, activating the interceptor for adk mode is logged."""
    monkeypatch.setenv("ANIMISM_DEBUG_MEDIA", "1")

    base_client = object()
    orchestrator = FakeOrchestrator()

    with caplog.at_level("INFO", logger="app.services.debug_tracer"):
        maybe_wrap_live_client_with_media_orchestrator(
            client=base_client,
            live_mode="adk",
            media_orchestrator=orchestrator,
        )

    assert any(
        "interceptor_active" in record.message
        for record in caplog.records
    ), f"Expected 'interceptor_active' for adk mode. Got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Media awareness feedback tests (Day 8 — agent conversational awareness)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_text_called_on_image_created() -> None:
    """When media.image.created fires, send_text is called on base stream
    to notify the model so it can respond in-voice."""
    base_stream = FakeBaseStream(
        events=[
            {
                "type": "tool_call",
                "tool": "generate_image",
                "scene_id": "scene-1",
                "prompt": "a blue robot",
            },
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    await _collect_events(stream)

    # The base stream should have received a send_text call for image awareness
    assert any(
        "image" in t.lower() and "scene-1" in t.lower()
        for t in base_stream.upstream_text
    ), f"Expected image awareness send_text. Got: {base_stream.upstream_text}"


@pytest.mark.asyncio
async def test_send_text_called_on_video_created() -> None:
    """When media.video.created fires, send_text is called on base stream
    to notify the model so it can respond in-voice."""
    base_stream = FakeBaseStream(
        events=[
            {
                "type": "tool_call",
                "tool": "generate_video",
                "scene_id": "scene-1",
                "args": {"video_prompt": "robot walks gently"},
            },
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    await _collect_events(stream)

    # The base stream should have received a send_text call for video awareness
    assert any(
        "video" in t.lower() and "scene-1" in t.lower()
        for t in base_stream.upstream_text
    ), f"Expected video awareness send_text. Got: {base_stream.upstream_text}"


@pytest.mark.asyncio
async def test_media_awareness_does_not_trigger_new_generation() -> None:
    """send_text media awareness must not cause any additional orchestrate_scene calls.
    Session lock (L7-007) remains enforced."""
    base_stream = FakeBaseStream(
        events=[
            {
                "type": "tool_call",
                "tool": "generate_image",
                "scene_id": "scene-1",
                "prompt": "a blue robot",
            },
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    await _collect_events(stream)

    # Only one image generation call, no re-trigger from awareness text
    assert len(orchestrator.image_calls) == 1
    assert orchestrator.video_calls == []
    assert orchestrator.calls == []


@pytest.mark.asyncio
async def test_no_send_text_for_drawing_in_progress() -> None:
    """drawing_in_progress events must NOT trigger send_text — only
    media.image.created and media.video.created should."""

    class SingleEventOrchestrator:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def generate_image_only(
            self,
            *,
            scene_id: str,
            image_prompt: str,
            event_sink: Any,
        ) -> None:
            self.calls.append({"scene_id": scene_id})
            await event_sink({"type": "drawing_in_progress", "scene_id": scene_id})

        async def generate_video_only(
            self,
            *,
            scene_id: str,
            video_prompt: str,
            event_sink: Any,
            imagen_image: Any | None = None,
        ) -> None:
            _ = scene_id, video_prompt, event_sink, imagen_image

        async def orchestrate_scene(
            self,
            *,
            scene_id: str,
            image_prompt: str,
            video_prompt: str,
            event_sink: Any,
        ) -> None:
            _ = scene_id, image_prompt, video_prompt, event_sink

    base_stream = FakeBaseStream(
        events=[
            {
                "type": "tool_call",
                "tool": "generate_image",
                "scene_id": "scene-1",
                "prompt": "test",
            },
        ]
    )
    orchestrator = SingleEventOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    await _collect_events(stream)

    # No send_text should have been called for drawing_in_progress
    assert base_stream.upstream_text == []


@pytest.mark.asyncio
async def test_send_text_awareness_is_safe_on_exception() -> None:
    """If send_text raises (e.g. stream closed), the event still queues
    for the frontend and no crash occurs."""

    class FailingSendTextStream(FakeBaseStream):
        async def send_text(self, text: str) -> None:
            raise ConnectionError("stream closed")

    base_stream = FailingSendTextStream(
        events=[
            {
                "type": "tool_call",
                "tool": "generate_image",
                "scene_id": "scene-1",
                "prompt": "test",
            },
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    events = await _collect_events(stream)

    # Even if send_text fails, the media event should still be in the queue
    assert any(
        isinstance(e, dict) and e.get("type") == "media.image.created"
        for e in events
    )


# ---------------------------------------------------------------------------
# Split generation tests (Day 8 — image-only / video-only governance)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_image_tool_triggers_image_only() -> None:
    """generate_image tool call must trigger generate_image_only, NOT
    orchestrate_scene.  No video should be auto-generated."""
    base_stream = FakeBaseStream(
        events=[
            {
                "type": "tool_call",
                "tool": "generate_image",
                "scene_id": "scene-1",
                "prompt": "a blue robot",
            },
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    events = await _collect_events(stream)

    # Should use generate_image_only, NOT orchestrate_scene
    assert len(orchestrator.image_calls) == 1
    assert orchestrator.calls == [], "orchestrate_scene should NOT be called"
    assert orchestrator.video_calls == [], "video should NOT be auto-triggered"

    # Only image events emitted (no media.video.created)
    assert any(isinstance(e, dict) and e.get("type") == "media.image.created" for e in events)
    assert not any(isinstance(e, dict) and e.get("type") == "media.video.created" for e in events)


@pytest.mark.asyncio
async def test_generate_video_tool_triggers_video_only() -> None:
    """generate_video tool call must trigger generate_video_only."""
    base_stream = FakeBaseStream(
        events=[
            {
                "type": "tool_call",
                "tool": "generate_video",
                "scene_id": "scene-1",
                "args": {"video_prompt": "robot walks gently"},
            },
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    events = await _collect_events(stream)

    # Should use generate_video_only
    assert len(orchestrator.video_calls) == 1
    assert orchestrator.calls == [], "orchestrate_scene should NOT be called"
    assert orchestrator.image_calls == [], "image should NOT be auto-triggered"

    # Only video event emitted
    assert any(isinstance(e, dict) and e.get("type") == "media.video.created" for e in events)
    assert not any(isinstance(e, dict) and e.get("type") == "media.image.created" for e in events)


@pytest.mark.asyncio
async def test_image_then_video_both_allowed_same_scene() -> None:
    """generate_image followed by generate_video for the same scene_id
    should both succeed — they are different media types."""
    base_stream = FakeBaseStream(
        events=[
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-1", "prompt": "a blue robot"},
            {"type": "tool_call", "tool": "generate_video", "scene_id": "scene-1", "args": {"video_prompt": "robot walks"}},
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    events = await _collect_events(stream)

    assert len(orchestrator.image_calls) == 1
    assert len(orchestrator.video_calls) == 1
    assert any(isinstance(e, dict) and e.get("type") == "media.image.created" for e in events)
    assert any(isinstance(e, dict) and e.get("type") == "media.video.created" for e in events)


@pytest.mark.asyncio
async def test_duplicate_image_tool_blocked_by_type_lock() -> None:
    """A second generate_image call in the same session must be blocked."""
    base_stream = FakeBaseStream(
        events=[
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-a", "prompt": "robot"},
            {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-b", "prompt": "cat"},
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    await _collect_events(stream)

    assert len(orchestrator.image_calls) == 1
    assert orchestrator.image_calls[0]["scene_id"] == "scene-a"


@pytest.mark.asyncio
async def test_duplicate_video_tool_blocked_by_type_lock() -> None:
    """A second generate_video call in the same session must be blocked."""
    base_stream = FakeBaseStream(
        events=[
            {"type": "tool_call", "tool": "generate_video", "scene_id": "scene-a", "args": {"video_prompt": "v1"}},
            {"type": "tool_call", "tool": "generate_video", "scene_id": "scene-b", "args": {"video_prompt": "v2"}},
        ]
    )
    orchestrator = FakeOrchestrator()
    stream = MediaToolCallInterceptingStream(
        base_stream=base_stream,
        media_orchestrator=orchestrator,
    )

    await _collect_events(stream)

    assert len(orchestrator.video_calls) == 1
    assert orchestrator.video_calls[0]["scene_id"] == "scene-a"
