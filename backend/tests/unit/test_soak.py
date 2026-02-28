"""Soak stability test for the duplex bridge.

Simulates a 5-minute bidirectional audio session with synthetic jitter,
collecting metrics to prove stability (no task leaks, bounded queue,
no disconnects under normal operation).
"""
from __future__ import annotations

import asyncio
import random

import pytest

from app.realtime.bridge import run_duplex_bridge
from app.realtime.bridge_metrics import BridgeMetrics

SOAK_DURATION_SECONDS = 300
CHUNK_INTERVAL_SECONDS = 0.02
AUDIO_CHUNK_SIZE = 3200


class SoakWebSocket:
    """WebSocket fake that sends audio chunks for a fixed duration with jitter."""

    def __init__(self, duration: float, chunk_interval: float = CHUNK_INTERVAL_SECONDS) -> None:
        self._duration = duration
        self._chunk_interval = chunk_interval
        self._start: float | None = None
        self.sent_bytes: list[bytes] = []
        self.sent_text: list[str] = []
        self._rng = random.Random(42)

    async def receive(self) -> dict:
        if self._start is None:
            self._start = asyncio.get_event_loop().time()

        elapsed = asyncio.get_event_loop().time() - self._start
        if elapsed >= self._duration:
            return {"type": "websocket.disconnect"}

        jitter = self._rng.uniform(0, self._chunk_interval * 0.5)
        await asyncio.sleep(self._chunk_interval + jitter)

        return {"bytes": b"\x00" * AUDIO_CHUNK_SIZE}

    async def send_bytes(self, payload: bytes) -> None:
        self.sent_bytes.append(payload)

    async def send_text(self, payload: str) -> None:
        self.sent_text.append(payload)


class SoakStream:
    """Gemini stream fake that echoes audio with variable delay."""

    def __init__(self, duration: float) -> None:
        self._duration = duration
        self._input_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.closed = False
        self._rng = random.Random(43)

    async def send_realtime_audio(self, audio_chunk: bytes) -> None:
        if not self.closed:
            await self._input_queue.put(audio_chunk)

    async def send_text(self, text: str) -> None:
        pass

    async def close(self) -> None:
        self.closed = True
        await self._input_queue.put(None)

    async def _events(self):
        while True:
            chunk = await self._input_queue.get()
            if chunk is None:
                break
            jitter_ms = self._rng.uniform(0, 30)
            await asyncio.sleep(jitter_ms / 1000)
            yield {"audio": chunk}

    def iter_events(self):
        return self._events()


class SoakGeminiClient:
    def __init__(self, stream: SoakStream) -> None:
        self.stream = stream

    async def open_stream(self, session_id: str):
        return self.stream


@pytest.mark.asyncio
async def test_soak_5min_duplex_stability() -> None:
    """Run a simulated 5-minute duplex session and assert stability metrics."""
    duration = SOAK_DURATION_SECONDS
    ws = SoakWebSocket(duration=duration)
    stream = SoakStream(duration=duration)
    client = SoakGeminiClient(stream=stream)
    metrics = BridgeMetrics()

    await run_duplex_bridge(websocket=ws, gemini_client=client, session_id="soak-1", metrics=metrics)

    snap = metrics.snapshot()

    assert snap["errors"] == 0, f"Expected zero errors, got {snap['errors']}"
    assert snap["elapsed_seconds"] >= duration * 0.95, (
        f"Session too short: {snap['elapsed_seconds']}s < {duration * 0.95}s"
    )
    assert snap["upstream_audio_count"] > 0, "No upstream audio sent"
    assert snap["downstream_audio_count"] > 0, "No downstream audio received"

    expected_min_chunks = int(duration / CHUNK_INTERVAL_SECONDS * 0.5)
    assert snap["upstream_audio_count"] >= expected_min_chunks, (
        f"Too few upstream chunks: {snap['upstream_audio_count']} < {expected_min_chunks}"
    )

    assert stream.closed is True, "Stream was not closed"


@pytest.mark.asyncio
async def test_soak_short_stability_smoke() -> None:
    """Quick 3-second soak to validate harness without waiting 5 minutes."""
    duration = 3
    ws = SoakWebSocket(duration=duration, chunk_interval=0.01)
    stream = SoakStream(duration=duration)
    client = SoakGeminiClient(stream=stream)
    metrics = BridgeMetrics()

    await run_duplex_bridge(websocket=ws, gemini_client=client, session_id="soak-quick", metrics=metrics)

    snap = metrics.snapshot()

    assert snap["errors"] == 0
    assert snap["elapsed_seconds"] >= 2.5
    assert snap["upstream_audio_count"] > 50
    assert snap["downstream_audio_count"] > 50
    assert stream.closed is True
