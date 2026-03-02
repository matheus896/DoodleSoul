"""
Gate 2 — Mocked Integration E2E: Real Bridge + Mocked Media Events

This suite validates stories I3.1, I3.2, and I3.3 from
validation-integration-mocked-story.md by exercising the REAL
``run_duplex_bridge()`` with mock WebSocket and Gemini streams that
simulate media generation events under realistic timing.

Key differences from Gate 1 (isolated):
    - Uses the actual bridge code path (asyncio.gather upstream/downstream).
    - Verifies audio forwarding integrity while media events arrive concurrently.
    - Validates event ordering and fallback isolation under out-of-order events.
    - Measures per-iteration timing to ensure no jank (>16ms blocking).

No production code is modified.  All media simulation lives in test mocks.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

# ── Backend path injection (minimal, tests-only) ──────────────────────────────
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.realtime.bridge import run_duplex_bridge  # noqa: E402
from app.realtime.bridge_metrics import BridgeMetrics  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# Test doubles — enhanced versions of the patterns from backend/tests/unit/
# ══════════════════════════════════════════════════════════════════════════════

PCM_SAMPLE_RATE = 16_000  # 16 kHz mono PCM input
PCM_FRAME_BYTES = 640  # 20 ms frame at 16 kHz 16-bit mono (320 samples × 2 bytes)
OUTPUT_SAMPLE_RATE = 24_000  # 24 kHz model output
OUTPUT_FRAME_BYTES = 960  # 20 ms frame at 24 kHz 16-bit mono


def _make_pcm_chunk(size: int = PCM_FRAME_BYTES) -> bytes:
    """Generate a deterministic PCM audio chunk of given size."""
    return bytes(range(256)) * (size // 256) + bytes(range(size % 256))


def _make_output_audio_chunk(size: int = OUTPUT_FRAME_BYTES) -> bytes:
    """Generate a deterministic model output audio chunk."""
    return bytes(range(256)) * (size // 256) + bytes(range(size % 256))


def _make_large_media_event(
    event_type: str,
    scene_id: str,
    *,
    payload_size_kb: int = 50,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a large media JSON event simulating Imagen/Veo results."""
    # Simulate a large base64 payload (image or video reference)
    fake_data = base64.b64encode(b"M" * (payload_size_kb * 1024)).decode("ascii")
    event: dict[str, Any] = {
        "type": event_type,
        "scene_id": scene_id,
        "media_url": f"mock://{scene_id}/{event_type}",
        "data_preview": fake_data[:200],  # Truncated for realism
        "payload_bytes": payload_size_kb * 1024,
    }
    if extra:
        event.update(extra)
    return event


# ── FakeWebSocket: simulates the server-side WS accepted connection ──────────

class IntegrationWebSocket:
    """
    A test double for the FastAPI WebSocket that feeds pre-recorded upstream
    messages and captures downstream output for assertions.
    """

    def __init__(self, upstream_messages: list[dict[str, Any]] | None = None) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.sent_bytes: list[bytes] = []
        self.sent_text: list[str] = []
        self._receive_timestamps: list[float] = []
        self._send_timestamps: list[float] = []

        # Enqueue supplied messages; sentinel will be added by feeder coroutine
        for msg in (upstream_messages or []):
            self._queue.put_nowait(msg)

    def enqueue_upstream(self, msg: dict[str, Any]) -> None:
        """Dynamically add a message for the bridge to receive."""
        self._queue.put_nowait(msg)

    async def receive(self) -> dict[str, Any]:
        msg = await self._queue.get()
        self._receive_timestamps.append(time.monotonic())
        return msg

    async def send_bytes(self, payload: bytes) -> None:
        self.sent_bytes.append(payload)
        self._send_timestamps.append(time.monotonic())

    async def send_text(self, payload: str) -> None:
        self.sent_text.append(payload)
        self._send_timestamps.append(time.monotonic())

    def parsed_text_events(self) -> list[dict[str, Any]]:
        """Return all sent_text payloads parsed as JSON dicts."""
        results = []
        for raw in self.sent_text:
            try:
                results.append(json.loads(raw))
            except json.JSONDecodeError:
                results.append({"raw": raw})
        return results


# ── Mock Gemini Stream: simulates audio + media events with timing ───────────

class MediaAwareStream:
    """
    A mock GeminiLiveStream that emits a scripted sequence of audio chunks
    and media events.  Supports configurable delays to simulate Imagen (5s)
    and Veo (30s) latency via compressed ``asyncio.sleep`` durations.

    The stream also records upstream audio for verification.

    After yielding all scripted events the iterator blocks on an internal
    ``_close_signal`` so that the bridge's ``downstream_task`` stays alive
    until ``upstream_task`` sends its disconnect.  ``stream.close()`` (called
    by the bridge's ``finally`` block) releases the wait, ensuring both
    tasks complete deterministically.
    """

    def __init__(
        self,
        event_script: list[dict[str, Any] | bytes],
        *,
        inter_event_delay: float = 0.0,
    ) -> None:
        self._script = list(event_script)
        self._inter_event_delay = inter_event_delay
        self.upstream_audio: list[bytes] = []
        self.upstream_text: list[str] = []
        self.closed = False
        self._iteration_times: list[float] = []
        self._close_signal = asyncio.Event()
        self._drained = asyncio.Event()

    async def send_realtime_audio(self, audio_chunk: bytes) -> None:
        self.upstream_audio.append(audio_chunk)

    async def send_text(self, text: str) -> None:
        self.upstream_text.append(text)

    async def _iter(self) -> AsyncIterator[dict[str, Any] | bytes]:
        for event in self._script:
            t0 = time.monotonic()
            yield event
            elapsed = time.monotonic() - t0
            self._iteration_times.append(elapsed)
            if self._inter_event_delay > 0:
                await asyncio.sleep(self._inter_event_delay)
            else:
                await asyncio.sleep(0)  # yield to event loop
        # Signal that all scripted events have been yielded
        self._drained.set()
        # Keep downstream alive until the bridge calls close()
        await self._close_signal.wait()

    def iter_events(self) -> AsyncIterator[dict[str, Any] | bytes]:
        return self._iter()

    async def close(self) -> None:
        self._close_signal.set()
        self.closed = True

    @property
    def max_iteration_ms(self) -> float:
        if not self._iteration_times:
            return 0.0
        return max(self._iteration_times) * 1000


class IntegrationGeminiClient:
    """Wraps a MediaAwareStream as a client for run_duplex_bridge."""

    def __init__(self, stream: MediaAwareStream) -> None:
        self.stream = stream

    async def open_stream(self, session_id: str) -> MediaAwareStream:
        return self.stream


# ── Helper: run bridge with feeding coroutine ────────────────────────────────

async def _run_bridge_with_feeding(
    *,
    websocket: IntegrationWebSocket,
    stream: MediaAwareStream,
    upstream_chunks: list[bytes],
    inter_chunk_delay: float = 0.001,
    timeout: float = 10.0,
) -> BridgeMetrics:
    """
    Run the real bridge while concurrently feeding upstream PCM chunks.
    Sends a disconnect sentinel after all chunks are fed.
    """
    client = IntegrationGeminiClient(stream)
    metrics = BridgeMetrics()

    async def feed_upstream() -> None:
        for chunk in upstream_chunks:
            websocket.enqueue_upstream({"bytes": chunk})
            await asyncio.sleep(inter_chunk_delay)
        # Signal disconnect after all audio has been sent
        websocket.enqueue_upstream({"type": "websocket.disconnect"})

    async def run_bridge() -> BridgeMetrics:
        return await run_duplex_bridge(
            websocket=websocket,
            gemini_client=client,
            session_id="gate2-integration",
            metrics=metrics,
        )

    _, result_metrics = await asyncio.wait_for(
        asyncio.gather(feed_upstream(), run_bridge()),
        timeout=timeout,
    )
    return result_metrics


# ══════════════════════════════════════════════════════════════════════════════
# I3.1 — WebSocket Pressure & Audio Integrity
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_i31_audio_integrity_under_media_pressure():
    """
    I3.1 AC1-AC4: Send continuous PCM audio upstream while the mock stream
    injects interleaved audio responses AND large media JSON events.
    Verify:
    - All upstream audio reaches the stream (no drops)
    - All downstream audio reaches the websocket (no drops)
    - Bridge metrics show zero errors
    - Media events are forwarded intact to the WS
    """
    num_audio_frames = 50  # 50 × 20ms = 1 second of audio
    num_media_events = 5   # 5 large media events interleaved

    # Build the downstream event script: interleave audio and media
    downstream_script: list[dict[str, Any] | bytes] = []
    for i in range(num_audio_frames):
        # Audio chunk (as raw bytes — direct path through bridge)
        downstream_script.append({"audio": _make_output_audio_chunk()})
        # Inject a media event every 10 audio frames
        if (i + 1) % 10 == 0:
            media_idx = (i + 1) // 10
            downstream_script.append(
                _make_large_media_event(
                    event_type="media.image.created" if media_idx <= 3 else "media.video.pending",
                    scene_id=f"scene-{media_idx}",
                    payload_size_kb=50,
                )
            )

    # Upstream audio chunks
    upstream_chunks = [_make_pcm_chunk() for _ in range(30)]

    # No inter_event_delay: downstream yields all events near-instantly via
    # asyncio.sleep(0), then blocks on _close_signal until upstream disconnects.
    stream = MediaAwareStream(downstream_script)
    websocket = IntegrationWebSocket()

    metrics = await _run_bridge_with_feeding(
        websocket=websocket,
        stream=stream,
        upstream_chunks=upstream_chunks,
    )

    # ── Assertions ──
    # All upstream audio was received by the stream
    assert len(stream.upstream_audio) == len(upstream_chunks), (
        f"Expected {len(upstream_chunks)} upstream chunks, got {len(stream.upstream_audio)}"
    )

    # Downstream audio was forwarded to websocket
    assert metrics.downstream_audio_count >= num_audio_frames, (
        f"Expected at least {num_audio_frames} downstream audio events, "
        f"got {metrics.downstream_audio_count}"
    )

    # Media events were forwarded as text
    text_events = websocket.parsed_text_events()
    media_events = [e for e in text_events if isinstance(e, dict) and "media_url" in e]
    assert len(media_events) == num_media_events, (
        f"Expected {num_media_events} media events forwarded, got {len(media_events)}"
    )

    # Zero errors in bridge metrics
    assert metrics.errors == 0, f"Bridge recorded {metrics.errors} errors"

    # Stream was properly closed
    assert stream.closed is True


@pytest.mark.asyncio
async def test_i31_zero_jank_during_media_arrival():
    """
    I3.1 AC3: Verify that no single downstream event processing blocks
    the event loop for more than 16ms (1 frame at 60fps).

    Uses a mock stream with large payloads and measures per-yield timing.
    """
    # Create a script with large media events (simulate heavy JSON)
    downstream_script: list[dict[str, Any] | bytes] = []
    for i in range(20):
        downstream_script.append({"audio": _make_output_audio_chunk()})
        if i % 4 == 0:
            downstream_script.append(
                _make_large_media_event(
                    event_type="media.image.created",
                    scene_id=f"perf-scene-{i}",
                    payload_size_kb=100,  # 100KB payload
                )
            )

    stream = MediaAwareStream(downstream_script, inter_event_delay=0.0)
    websocket = IntegrationWebSocket()

    # Wrap bridge to measure downstream processing times
    send_times: list[float] = []
    original_send_text = websocket.send_text
    original_send_bytes = websocket.send_bytes

    async def timed_send_text(payload: str) -> None:
        t0 = time.monotonic()
        await original_send_text(payload)
        send_times.append((time.monotonic() - t0) * 1000)

    async def timed_send_bytes(payload: bytes) -> None:
        t0 = time.monotonic()
        await original_send_bytes(payload)
        send_times.append((time.monotonic() - t0) * 1000)

    websocket.send_text = timed_send_text  # type: ignore[assignment]
    websocket.send_bytes = timed_send_bytes  # type: ignore[assignment]

    await _run_bridge_with_feeding(
        websocket=websocket,
        stream=stream,
        upstream_chunks=[_make_pcm_chunk() for _ in range(5)],
    )

    # No single send should block for >16ms
    max_send_ms = max(send_times) if send_times else 0
    assert max_send_ms < 16, (
        f"Max send time was {max_send_ms:.2f}ms, exceeds 16ms jank threshold"
    )

    # Stream iteration itself should not block
    assert stream.max_iteration_ms < 16, (
        f"Max iteration time was {stream.max_iteration_ms:.2f}ms, exceeds 16ms"
    )


@pytest.mark.asyncio
async def test_i31_audio_buffer_worklet_continuity():
    """
    I3.1 AC4: Simulate AudioWorklet buffer scenario — verify that audio
    chunks arrive at a steady rate even when media events are injected,
    ensuring no buffer underflow condition.

    We measure the inter-arrival time of downstream audio bytes at the
    websocket level and assert consistency.
    """
    num_audio = 40
    downstream_script: list[dict[str, Any] | bytes] = []
    for i in range(num_audio):
        downstream_script.append({"audio": _make_output_audio_chunk()})
        # Inject bursts of media events mid-stream
        if i == 15 or i == 25:
            for j in range(3):
                downstream_script.append(
                    _make_large_media_event(
                        event_type="media.image.created",
                        scene_id=f"burst-{i}-{j}",
                        payload_size_kb=80,
                    )
                )

    # No inter_event_delay: events yield instantly, then stream waits on
    # _close_signal so upstream can finish.
    stream = MediaAwareStream(downstream_script)
    websocket = IntegrationWebSocket()

    # Track audio arrival timestamps
    audio_arrival_times: list[float] = []
    original_send_bytes = websocket.send_bytes

    async def tracking_send_bytes(payload: bytes) -> None:
        audio_arrival_times.append(time.monotonic())
        await original_send_bytes(payload)

    websocket.send_bytes = tracking_send_bytes  # type: ignore[assignment]

    await _run_bridge_with_feeding(
        websocket=websocket,
        stream=stream,
        upstream_chunks=[_make_pcm_chunk() for _ in range(10)],
    )

    # Verify audio continuity: no gaps > 50ms between consecutive audio arrivals
    # (In production, jitter buffer absorbs up to 500ms, so 50ms is conservative)
    assert len(audio_arrival_times) >= num_audio, (
        f"Expected {num_audio} audio arrivals, got {len(audio_arrival_times)}"
    )

    gaps: list[float] = []
    for idx in range(1, len(audio_arrival_times)):
        gap_ms = (audio_arrival_times[idx] - audio_arrival_times[idx - 1]) * 1000
        gaps.append(gap_ms)

    max_gap = max(gaps) if gaps else 0
    assert max_gap < 50, (
        f"Max inter-audio gap was {max_gap:.2f}ms — indicates potential underflow. "
        f"Threshold: 50ms"
    )


# ══════════════════════════════════════════════════════════════════════════════
# I3.2 — Narratively-Aware Latency Masking
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_i32_drawing_in_progress_signal_forwarded():
    """
    I3.2 AC1: When mock media tool is triggered, the stream injects a
    system-level "drawing in progress" signal. Verify it reaches the WS.
    """
    downstream_script: list[dict[str, Any] | bytes] = [
        # Normal audio
        {"audio": _make_output_audio_chunk()},
        {"audio": _make_output_audio_chunk()},
        # Media tool triggered → drawing-in-progress signal
        {
            "type": "system_instruction",
            "instruction": "drawing_in_progress",
            "message": "Drawing in progress... Keep the child talking for 10 more seconds.",
            "scene_id": "scene-A",
        },
        # More audio (AI keeps talking)
        {"audio": _make_output_audio_chunk()},
        {"audio": _make_output_audio_chunk()},
        # Narrative acknowledgment
        {
            "type": "text",
            "text": "I'm working on your blue robot right now!",
        },
        {"audio": _make_output_audio_chunk()},
        # Image result arrives ~5s later (compressed to instant in test)
        _make_large_media_event(
            event_type="media.image.created",
            scene_id="scene-A",
        ),
    ]

    stream = MediaAwareStream(downstream_script)
    websocket = IntegrationWebSocket()

    await _run_bridge_with_feeding(
        websocket=websocket,
        stream=stream,
        upstream_chunks=[_make_pcm_chunk() for _ in range(5)],
    )

    text_events = websocket.parsed_text_events()

    # Verify drawing-in-progress signal reached WS
    instruction_events = [
        e for e in text_events
        if isinstance(e, dict) and e.get("type") == "system_instruction"
    ]
    assert len(instruction_events) >= 1, "drawing_in_progress signal not forwarded"
    assert instruction_events[0]["instruction"] == "drawing_in_progress"

    # Verify narrative text was forwarded
    text_messages = [
        e for e in text_events
        if isinstance(e, dict) and e.get("type") == "text"
    ]
    assert any("blue robot" in e.get("text", "") for e in text_messages), (
        "Narrative acknowledgment text not forwarded"
    )

    # Verify media event also arrived
    media_events = [
        e for e in text_events
        if isinstance(e, dict) and "media_url" in e
    ]
    assert len(media_events) >= 1, "media.image.created event not forwarded"


@pytest.mark.asyncio
async def test_i32_media_delayed_signal_after_timeout():
    """
    I3.2 AC3: Simulate a Veo job that hits the 30s mark. Verify the backend
    emits a ``media_delayed`` signal and the AI pivots to an engagement
    message, all forwarded through the real bridge.
    """
    downstream_script: list[dict[str, Any] | bytes] = [
        {"audio": _make_output_audio_chunk()},
        # Tool triggered — video generation starts
        {
            "type": "system_instruction",
            "instruction": "drawing_in_progress",
            "message": "Creating your video magic... Keep the child talking.",
            "scene_id": "scene-V1",
            "media_type": "video",
        },
        # Audio continues (narrative masking)
        {"audio": _make_output_audio_chunk()},
        {"audio": _make_output_audio_chunk()},
        # 30s timeout reached → media_delayed signal
        {
            "type": "media_delayed",
            "scene_id": "scene-V1",
            "elapsed_seconds": 30,
            "message": "This is a big magic trick, it's taking a bit longer. What should we do next?",
        },
        # AI pivot message
        {
            "type": "text",
            "text": "This is a big magic trick! While we wait, what other adventure should we plan?",
        },
        {"audio": _make_output_audio_chunk()},
        # Eventually video completes
        _make_large_media_event(
            event_type="media.video.completed",
            scene_id="scene-V1",
            extra={"elapsed_seconds": 45},
        ),
    ]

    stream = MediaAwareStream(downstream_script)
    websocket = IntegrationWebSocket()

    await _run_bridge_with_feeding(
        websocket=websocket,
        stream=stream,
        upstream_chunks=[_make_pcm_chunk() for _ in range(5)],
    )

    text_events = websocket.parsed_text_events()

    # Verify media_delayed signal
    delayed_events = [
        e for e in text_events
        if isinstance(e, dict) and e.get("type") == "media_delayed"
    ]
    assert len(delayed_events) >= 1, "media_delayed signal not forwarded"
    assert delayed_events[0]["scene_id"] == "scene-V1"
    assert delayed_events[0]["elapsed_seconds"] == 30

    # Verify the pivot text arrived
    text_msgs = [
        e for e in text_events
        if isinstance(e, dict) and e.get("type") == "text"
    ]
    assert any("magic trick" in e.get("text", "").lower() for e in text_msgs), (
        "AI pivot message not forwarded"
    )

    # Verify video eventually completed
    video_events = [
        e for e in text_events
        if isinstance(e, dict) and e.get("type") == "media.video.completed"
    ]
    assert len(video_events) >= 1, "media.video.completed event not forwarded"


@pytest.mark.asyncio
async def test_i32_audio_continues_during_all_signals():
    """
    I3.2 combined: Audio output must continue flowing during all instruction
    and media_delayed signals — no interruption to the playback stream.
    """
    downstream_script: list[dict[str, Any] | bytes] = []
    audio_count = 0

    # Phase 1: pre-signal audio
    for _ in range(10):
        downstream_script.append({"audio": _make_output_audio_chunk()})
        audio_count += 1

    # Signal injection
    downstream_script.append({
        "type": "system_instruction",
        "instruction": "drawing_in_progress",
        "message": "Keep talking.",
        "scene_id": "sc-1",
    })

    # Phase 2: mid-signal audio
    for _ in range(10):
        downstream_script.append({"audio": _make_output_audio_chunk()})
        audio_count += 1

    # Delayed signal
    downstream_script.append({
        "type": "media_delayed",
        "scene_id": "sc-1",
        "elapsed_seconds": 30,
        "message": "Still working...",
    })

    # Phase 3: post-delay audio
    for _ in range(10):
        downstream_script.append({"audio": _make_output_audio_chunk()})
        audio_count += 1

    stream = MediaAwareStream(downstream_script)
    websocket = IntegrationWebSocket()

    metrics = await _run_bridge_with_feeding(
        websocket=websocket,
        stream=stream,
        upstream_chunks=[_make_pcm_chunk() for _ in range(5)],
    )

    # All audio events delivered
    assert metrics.downstream_audio_count == audio_count, (
        f"Expected {audio_count} audio events, got {metrics.downstream_audio_count}. "
        "Audio was interrupted during signal injection."
    )
    assert metrics.errors == 0


# ══════════════════════════════════════════════════════════════════════════════
# I3.3 — State-Machine Synchronization (Race Condition Test)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_i33_out_of_order_media_events_all_forwarded():
    """
    I3.3 AC1-AC2: Two media jobs triggered in sequence but results arrive
    in reverse order (scene-2 before scene-1).  Verify both events reach
    the websocket and the ordering is traceable via scene_id + timestamps.
    """
    downstream_script: list[dict[str, Any] | bytes] = [
        # Audio flow
        {"audio": _make_output_audio_chunk()},
        # Tool call for scene-1 (Imagen)
        {
            "type": "tool_call",
            "tool": "generate_image",
            "scene_id": "scene-1",
            "sequence": 1,
        },
        {"audio": _make_output_audio_chunk()},
        # Tool call for scene-2 (Imagen) — child changed topic
        {
            "type": "tool_call",
            "tool": "generate_image",
            "scene_id": "scene-2",
            "sequence": 2,
        },
        {"audio": _make_output_audio_chunk()},
        # !! scene-2 result arrives FIRST (out of order from "network")
        _make_large_media_event(
            event_type="media.image.created",
            scene_id="scene-2",
            extra={"sequence": 2, "arrival_order": 1},
        ),
        {"audio": _make_output_audio_chunk()},
        # scene-1 result arrives SECOND
        _make_large_media_event(
            event_type="media.image.created",
            scene_id="scene-1",
            extra={"sequence": 1, "arrival_order": 2},
        ),
        {"audio": _make_output_audio_chunk()},
    ]

    stream = MediaAwareStream(downstream_script)
    websocket = IntegrationWebSocket()

    metrics = await _run_bridge_with_feeding(
        websocket=websocket,
        stream=stream,
        upstream_chunks=[_make_pcm_chunk() for _ in range(5)],
    )

    text_events = websocket.parsed_text_events()

    # Both media events forwarded
    media_events = [
        e for e in text_events
        if isinstance(e, dict) and e.get("type") == "media.image.created"
    ]
    assert len(media_events) == 2, f"Expected 2 media events, got {len(media_events)}"

    # Scene IDs traceable
    scene_ids = [e["scene_id"] for e in media_events]
    assert "scene-1" in scene_ids
    assert "scene-2" in scene_ids

    # Arrival order preserved (scene-2 arrived first in downstream)
    assert media_events[0]["scene_id"] == "scene-2", (
        "First media event should be scene-2 (out-of-order arrival)"
    )
    assert media_events[1]["scene_id"] == "scene-1", (
        "Second media event should be scene-1 (late arrival)"
    )

    # Tool calls also forwarded for traceability
    tool_calls = [
        e for e in text_events
        if isinstance(e, dict) and e.get("type") == "tool_call"
    ]
    assert len(tool_calls) == 2, "Both tool_call events should be forwarded"
    assert tool_calls[0]["sequence"] == 1
    assert tool_calls[1]["sequence"] == 2

    # Audio continued throughout
    assert metrics.downstream_audio_count >= 5
    assert metrics.errors == 0


@pytest.mark.asyncio
async def test_i33_fallback_isolated_per_scene():
    """
    I3.3 AC3: fallback_active (Ken Burns) is scene-scoped.  Scene-A has
    completed media, Scene-B is delayed.  Only Scene-B should show fallback.

    This test validates the state tracking logic at the event stream level.
    """

    @dataclass
    class SceneState:
        scene_id: str
        status: str = "pending"
        fallback_active: bool = False
        elapsed_seconds: float = 0.0

    scene_tracker: dict[str, SceneState] = {}

    def process_event(event: dict[str, Any], elapsed: float) -> None:
        """Simulate frontend state machine processing."""
        scene_id = event.get("scene_id")
        if not scene_id:
            return

        if scene_id not in scene_tracker:
            scene_tracker[scene_id] = SceneState(scene_id=scene_id)

        state = scene_tracker[scene_id]
        event_type = event.get("type", "")

        if event_type == "tool_call":
            state.status = "generating"
            state.elapsed_seconds = 0.0
        elif event_type == "media.image.created":
            state.status = "image_ready"
            state.fallback_active = False
        elif event_type == "media.video.pending":
            state.status = "video_pending"
            state.elapsed_seconds = elapsed
        elif event_type == "media.video.completed":
            state.status = "video_ready"
            state.fallback_active = False
        elif event_type == "media_delayed":
            state.fallback_active = True
            state.status = "fallback_active"

    # Build event sequence:
    # Scene-A: image created quickly, video completes
    # Scene-B: image created, video delayed >30s → fallback
    downstream_script: list[dict[str, Any] | bytes] = [
        {"audio": _make_output_audio_chunk()},
        {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-A", "sequence": 1},
        {"type": "tool_call", "tool": "generate_image", "scene_id": "scene-B", "sequence": 2},
        {"audio": _make_output_audio_chunk()},
        # Scene-A image ready
        _make_large_media_event("media.image.created", "scene-A"),
        {"audio": _make_output_audio_chunk()},
        # Scene-B image ready
        _make_large_media_event("media.image.created", "scene-B"),
        {"audio": _make_output_audio_chunk()},
        # Video for scene-A completes quickly
        _make_large_media_event(
            "media.video.completed",
            "scene-A",
            extra={"elapsed_seconds": 12},
        ),
        {"audio": _make_output_audio_chunk()},
        # Video for scene-B is delayed → media_delayed signal
        {
            "type": "media_delayed",
            "scene_id": "scene-B",
            "elapsed_seconds": 30,
            "message": "Video for scene-B is still processing...",
        },
        {"audio": _make_output_audio_chunk()},
    ]

    stream = MediaAwareStream(downstream_script)
    websocket = IntegrationWebSocket()

    await _run_bridge_with_feeding(
        websocket=websocket,
        stream=stream,
        upstream_chunks=[_make_pcm_chunk() for _ in range(5)],
    )

    # Process all forwarded events through state machine
    text_events = websocket.parsed_text_events()
    sim_elapsed = 0.0
    for event in text_events:
        sim_elapsed += 1.0  # Simulated time progression
        process_event(event, sim_elapsed)

    # ── Scene-level assertions ──
    assert "scene-A" in scene_tracker, "Scene-A should exist in tracker"
    assert "scene-B" in scene_tracker, "Scene-B should exist in tracker"

    scene_a = scene_tracker["scene-A"]
    scene_b = scene_tracker["scene-B"]

    # Scene-A: completed, no fallback
    assert scene_a.status == "video_ready", (
        f"Scene-A should be video_ready, got {scene_a.status}"
    )
    assert scene_a.fallback_active is False, "Scene-A should NOT have fallback active"

    # Scene-B: delayed, fallback active
    assert scene_b.fallback_active is True, "Scene-B SHOULD have fallback active"
    assert scene_b.status == "fallback_active", (
        f"Scene-B should be fallback_active, got {scene_b.status}"
    )


@pytest.mark.asyncio
async def test_i33_bridge_metrics_consistent_under_mixed_load():
    """
    Cross-cutting: verify BridgeMetrics tallies are exactly correct under
    mixed audio + media + text load through the real bridge.
    """
    n_audio_down = 20
    n_media = 4
    n_text = 2
    n_audio_up = 15

    downstream_script: list[dict[str, Any] | bytes] = []
    for i in range(n_audio_down):
        downstream_script.append({"audio": _make_output_audio_chunk()})
        if i == 5 or i == 10 or i == 14 or i == 18:
            downstream_script.append(
                _make_large_media_event("media.image.created", f"m-{i}")
            )
    # Add text events
    downstream_script.append({"type": "text", "text": "Hello from the model"})
    downstream_script.append({"type": "text", "text": "Still here"})

    stream = MediaAwareStream(downstream_script)
    websocket = IntegrationWebSocket()

    metrics = await _run_bridge_with_feeding(
        websocket=websocket,
        stream=stream,
        upstream_chunks=[_make_pcm_chunk() for _ in range(n_audio_up)],
    )

    # Metrics validation
    assert metrics.upstream_audio_count == n_audio_up
    assert metrics.downstream_audio_count == n_audio_down
    assert metrics.downstream_text_count == n_text
    assert metrics.errors == 0
    assert metrics.downstream_bytes_total > 0
    assert metrics.upstream_bytes_total == n_audio_up * PCM_FRAME_BYTES
    assert stream.closed is True
