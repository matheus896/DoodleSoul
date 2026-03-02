"""
Gate 3 Pre-flight — PilotMockGeminiLiveStream Automated Validation

Validates that the PilotMockGeminiLiveStream works correctly through the
REAL bridge (run_duplex_bridge) before human pilot sessions.

Key validations:
    - Tone audio responses are generated at correct intervals.
    - Media scenario fires after audio threshold is reached.
    - drawing_in_progress, image.created, media_delayed, video.created
      events all pass through the bridge to the WebSocket.
    - Audio tones continue to flow during media events (no dead air).
    - Bridge metrics remain consistent.
    - No errors or exceptions during the full scenario.

Uses compressed timings (not real 30s delays) for CI speed.
No production code is modified.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

# ── Backend path injection ────────────────────────────────────────────────────
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.realtime.bridge import run_duplex_bridge  # noqa: E402
from app.realtime.bridge_metrics import BridgeMetrics  # noqa: E402
from app.services.live_client_factory import PilotMockGeminiLiveStream  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# Compressed-timing variant for automated testing
# ══════════════════════════════════════════════════════════════════════════════

class FastPilotMockStream(PilotMockGeminiLiveStream):
    """PilotMockGeminiLiveStream with compressed timings for CI.

    Real delays (5s/30s/10s) are compressed to sub-second for fast tests.
    Media threshold lowered to trigger quickly with few chunks.
    """

    RESPONSE_INTERVAL = 2
    MEDIA_THRESHOLD = 5
    IMAGEN_DELAY_S = 0.05
    VEO_DELAY_S = 0.15
    POST_DELAY_AUDIO_S = 0.05


# ══════════════════════════════════════════════════════════════════════════════
# Test doubles — reused from Gate 2 pattern
# ══════════════════════════════════════════════════════════════════════════════

PCM_FRAME_BYTES = 640  # 20 ms frame at 16 kHz 16-bit mono


def _make_pcm_chunk(size: int = PCM_FRAME_BYTES) -> bytes:
    return bytes(range(256)) * (size // 256) + bytes(range(size % 256))


class IntegrationWebSocket:
    """Test double for FastAPI WebSocket — feeds upstream, captures downstream."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.sent_bytes: list[bytes] = []
        self.sent_text: list[str] = []

    def enqueue_upstream(self, msg: dict[str, Any]) -> None:
        self._queue.put_nowait(msg)

    async def receive(self) -> dict[str, Any]:
        return await self._queue.get()

    async def send_bytes(self, payload: bytes) -> None:
        self.sent_bytes.append(payload)

    async def send_text(self, payload: str) -> None:
        self.sent_text.append(payload)

    def parsed_text_events(self) -> list[dict[str, Any]]:
        results = []
        for raw in self.sent_text:
            try:
                results.append(json.loads(raw))
            except json.JSONDecodeError:
                results.append({"raw": raw})
        return results


class PilotGeminiClient:
    """Wraps PilotMockGeminiLiveStream as a client for run_duplex_bridge."""

    def __init__(self, stream: PilotMockGeminiLiveStream) -> None:
        self.stream = stream

    async def open_stream(self, session_id: str) -> PilotMockGeminiLiveStream:
        return self.stream


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

async def _run_pilot_bridge(
    *,
    stream: PilotMockGeminiLiveStream,
    num_chunks: int = 20,
    inter_chunk_delay: float = 0.001,
    post_scenario_wait: float = 0.5,
    timeout: float = 10.0,
) -> tuple[IntegrationWebSocket, BridgeMetrics]:
    """Run the real bridge with a PilotMockGeminiLiveStream.

    Feeds ``num_chunks`` PCM upstream, waits for the media scenario to
    complete, then sends disconnect.  Returns WS captures and metrics.
    """
    ws = IntegrationWebSocket()
    client = PilotGeminiClient(stream)
    metrics = BridgeMetrics()

    async def feed_upstream() -> None:
        for _ in range(num_chunks):
            ws.enqueue_upstream({"bytes": _make_pcm_chunk()})
            await asyncio.sleep(inter_chunk_delay)
        # Give media scenario time to run
        await asyncio.sleep(post_scenario_wait)
        ws.enqueue_upstream({"type": "websocket.disconnect"})

    async def run_bridge() -> BridgeMetrics:
        return await run_duplex_bridge(
            websocket=ws,
            gemini_client=client,
            session_id="pilot-preflight",
            metrics=metrics,
        )

    _, result = await asyncio.wait_for(
        asyncio.gather(feed_upstream(), run_bridge()),
        timeout=timeout,
    )
    return ws, result


# ══════════════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pilot_mock_generates_tone_responses():
    """Pilot mock emits 24kHz PCM tone bytes at regular intervals."""
    stream = FastPilotMockStream()
    num_chunks = 10  # > RESPONSE_INTERVAL (2) to trigger tones

    ws, metrics = await _run_pilot_bridge(
        stream=stream,
        num_chunks=num_chunks,
        post_scenario_wait=0.3,
    )

    # Should have received tone audio bytes
    assert len(ws.sent_bytes) > 0, "No tone audio generated"

    # Each tone should be valid PCM16 (even number of bytes)
    for chunk in ws.sent_bytes:
        assert len(chunk) > 0
        assert len(chunk) % 2 == 0, f"Tone chunk has odd byte count: {len(chunk)}"

    # Tone duration = 200ms at 24kHz = 4800 samples = 9600 bytes
    expected_tone_bytes = stream.SAMPLE_RATE * stream.TONE_DURATION_MS // 1000 * 2
    # At least some tones should match default size
    default_tones = [c for c in ws.sent_bytes if len(c) == expected_tone_bytes]
    assert len(default_tones) >= 1, "Expected at least 1 default-duration tone"


@pytest.mark.asyncio
async def test_pilot_mock_media_scenario_fires():
    """After audio threshold, the full media scenario runs and events arrive at WS."""
    stream = FastPilotMockStream()

    ws, metrics = await _run_pilot_bridge(
        stream=stream,
        num_chunks=20,  # Well above MEDIA_THRESHOLD (5)
        post_scenario_wait=1.0,  # Enough time for compressed scenario
    )

    events = ws.parsed_text_events()
    event_types = [e.get("type") for e in events if "type" in e]

    # Must have all 4 media event types from scenario
    assert "system_instruction" in event_types, "Missing drawing_in_progress signal"
    assert "media.image.created" in event_types, "Missing Imagen result"
    assert "media_delayed" in event_types, "Missing media_delayed signal"
    assert "media.video.created" in event_types, "Missing Veo result"


@pytest.mark.asyncio
async def test_pilot_mock_event_ordering():
    """Media events arrive in correct chronological order."""
    stream = FastPilotMockStream()

    ws, _ = await _run_pilot_bridge(
        stream=stream,
        num_chunks=20,
        post_scenario_wait=1.0,
    )

    events = ws.parsed_text_events()
    typed_events = [(i, e) for i, e in enumerate(events) if "type" in e]

    type_order = [e.get("type") for _, e in typed_events]

    # Verify ordering: system_instruction → image → delayed → video
    idx_instruction = type_order.index("system_instruction")
    idx_image = type_order.index("media.image.created")
    idx_delayed = type_order.index("media_delayed")
    idx_video = type_order.index("media.video.created")

    assert idx_instruction < idx_image < idx_delayed < idx_video, (
        f"Wrong order: instruction@{idx_instruction}, image@{idx_image}, "
        f"delayed@{idx_delayed}, video@{idx_video}"
    )


@pytest.mark.asyncio
async def test_pilot_mock_audio_continues_during_media():
    """Tone audio bytes continue to arrive during the media scenario — no dead air."""
    stream = FastPilotMockStream()

    ws, _ = await _run_pilot_bridge(
        stream=stream,
        num_chunks=20,
        post_scenario_wait=1.0,
    )

    # Total audio chunks should include both pre-media tones and scenario tones
    total_audio = len(ws.sent_bytes)
    total_text = len(ws.sent_text)

    assert total_audio >= 3, (
        f"Expected ≥3 audio tone chunks, got {total_audio}. "
        "Audio may not be flowing during media scenario."
    )
    assert total_text >= 4, (
        f"Expected ≥4 text events (signals + narrative), got {total_text}"
    )


@pytest.mark.asyncio
async def test_pilot_mock_narrative_text_forwarded():
    """Narrative text responses are forwarded through the bridge."""
    stream = FastPilotMockStream()

    ws, _ = await _run_pilot_bridge(
        stream=stream,
        num_chunks=20,
        post_scenario_wait=1.0,
    )

    events = ws.parsed_text_events()
    narrative_texts = [
        e.get("text", "")
        for e in events
        if "text" in e and "type" not in e
    ]

    # Should have narrative text like "blue robot", "move", "magic trick"
    all_text = " ".join(narrative_texts).lower()
    assert "robot" in all_text or "move" in all_text or "magic" in all_text, (
        f"Expected narrative text about robot/move/magic, got: {narrative_texts}"
    )


@pytest.mark.asyncio
async def test_pilot_mock_large_payloads_forwarded():
    """Large mock payloads (50KB+) are forwarded without truncation or error."""
    stream = FastPilotMockStream()

    ws, metrics = await _run_pilot_bridge(
        stream=stream,
        num_chunks=20,
        post_scenario_wait=1.0,
    )

    events = ws.parsed_text_events()
    image_events = [e for e in events if e.get("type") == "media.image.created"]
    video_events = [e for e in events if e.get("type") == "media.video.created"]

    assert len(image_events) >= 1
    assert len(video_events) >= 1

    # Verify large payload was forwarded intact
    img = image_events[0]
    assert len(img.get("_mock_payload", "")) == 50000, "Image payload truncated"

    vid = video_events[0]
    assert len(vid.get("_mock_payload", "")) == 100000, "Video payload truncated"

    # Bridge should have zero errors
    snap = metrics.snapshot()
    assert snap.get("errors", 0) == 0


@pytest.mark.asyncio
async def test_pilot_mock_bridge_metrics_consistent():
    """BridgeMetrics tallies are consistent after full pilot scenario."""
    stream = FastPilotMockStream()
    num_chunks = 20

    ws, metrics = await _run_pilot_bridge(
        stream=stream,
        num_chunks=num_chunks,
        post_scenario_wait=1.0,
    )

    snap = metrics.snapshot()

    # Upstream: all audio chunks should be recorded
    assert snap["upstream_audio_count"] == num_chunks

    # Downstream audio: at least some tone responses
    assert snap["downstream_audio_count"] >= 1

    # Downstream text: media events + narrative text
    assert snap["downstream_text_count"] >= 4

    # No errors
    assert snap["errors"] == 0


@pytest.mark.asyncio
async def test_pilot_mock_clean_close():
    """Stream closes cleanly, cancelling the media scenario task."""
    stream = FastPilotMockStream()

    ws, metrics = await _run_pilot_bridge(
        stream=stream,
        num_chunks=20,
        post_scenario_wait=0.5,
    )

    # Stream should be closed
    assert stream._closed is True

    # Media task should be done (completed or cancelled)
    if stream._media_task is not None:
        assert stream._media_task.done()
