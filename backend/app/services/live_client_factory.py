from __future__ import annotations

import asyncio
import math
import os
import struct
from typing import Any, AsyncIterator

from app.config.env_loader import load_env_once
from app.services.gemini_client import GeminiLiveClient


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _generate_pcm16_tone(
    *,
    sample_rate: int = 24000,
    duration_ms: int = 200,
    freq_hz: int = 330,
    amplitude: int = 4000,
) -> bytes:
    """Generate a short PCM-16 LE sine wave.

    Default amplitude is intentionally low (~-18 dBFS) to satisfy NFR9
    (avoid sudden audio peaks >75 dB / sensory-safe).
    """
    num_samples = sample_rate * duration_ms // 1000
    buf = bytearray(num_samples * 2)
    for i in range(num_samples):
        t = i / sample_rate
        val = int(amplitude * math.sin(2.0 * math.pi * freq_hz * t))
        struct.pack_into("<h", buf, i * 2, max(-32768, min(32767, val)))
    return bytes(buf)


# ---------------------------------------------------------------------------
# MockGeminiLiveStream — simple echo mock (existing, unchanged behaviour)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# PilotMockGeminiLiveStream — Gate 3 human pilot sessions
# ---------------------------------------------------------------------------

class PilotMockGeminiLiveStream:
    """Mock stream that simulates realistic Gemini Live + media pressure.

    Designed for Gate 3 human pilot sessions:
    1. Generates periodic gentle 24 kHz PCM tone responses.
    2. After a configurable audio threshold, runs a scripted media-event
       scenario (drawing_in_progress → Imagen result → media_delayed → Veo
       result) with realistic timing.
    3. Keeps tone responses flowing during media delays —
       proves audio continuity is unbroken.

    Activate via ``ANIMISM_LIVE_MODE=pilot``.
    """

    RESPONSE_INTERVAL: int = 5       # Reply every N audio chunks
    MEDIA_THRESHOLD: int = 30        # Start media scenario after N chunks
    TONE_FREQ_HZ: int = 330          # E4 — gentle
    TONE_AMPLITUDE: int = 4000       # Low amplitude (NFR9 safe)
    TONE_DURATION_MS: int = 200      # Short burst
    SAMPLE_RATE: int = 24000         # Must match frontend AudioContext

    # Timing for scripted media scenario (seconds)
    IMAGEN_DELAY_S: float = 5.0
    VEO_DELAY_S: float = 30.0
    POST_DELAY_AUDIO_S: float = 10.0

    def __init__(self) -> None:
        self._events: asyncio.Queue[dict[str, Any] | bytes | None] = asyncio.Queue()
        self._closed = False
        self._audio_chunks_received = 0
        self._media_task: asyncio.Task[None] | None = None

    # -- upstream interface (called by bridge) --------------------------------

    async def send_realtime_audio(self, audio_chunk: bytes) -> None:
        if self._closed:
            return
        self._audio_chunks_received += 1

        # Periodic tone response (simulates AI speech)
        if self._audio_chunks_received % self.RESPONSE_INTERVAL == 0:
            await self._events.put(
                _generate_pcm16_tone(
                    sample_rate=self.SAMPLE_RATE,
                    duration_ms=self.TONE_DURATION_MS,
                    freq_hz=self.TONE_FREQ_HZ,
                    amplitude=self.TONE_AMPLITUDE,
                )
            )

        # Start media scenario once after threshold
        if (
            self._media_task is None
            and self._audio_chunks_received >= self.MEDIA_THRESHOLD
        ):
            self._media_task = asyncio.create_task(self._run_media_scenario())

    async def send_text(self, text: str) -> None:
        if self._closed:
            return
        await self._events.put({"text": f"pilot-echo:{text}"})

    # -- downstream interface (consumed by bridge) ----------------------------

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
        if self._media_task and not self._media_task.done():
            self._media_task.cancel()
            try:
                await self._media_task
            except asyncio.CancelledError:
                pass
        await self._events.put(None)

    # -- scripted media scenario ----------------------------------------------

    async def _emit_tone(self, duration_ms: int = 150) -> None:
        """Emit a short tone (non-blocking helper)."""
        await self._events.put(
            _generate_pcm16_tone(
                sample_rate=self.SAMPLE_RATE,
                duration_ms=duration_ms,
                freq_hz=self.TONE_FREQ_HZ,
                amplitude=self.TONE_AMPLITUDE,
            )
        )

    async def _run_media_scenario(self) -> None:
        """Scripted media event sequence simulating Imagen + Veo pipeline."""
        try:
            # --- Phase 1: drawing_in_progress (Imagen queued) ----------------
            await self._events.put({
                "type": "system_instruction",
                "text": "drawing_in_progress",
                "scene_id": "scene-1",
            })
            await self._events.put({
                "text": "I'm drawing a picture of your blue robot right now!",
            })

            # Tones during Imagen delay (≈5 s)
            imagen_steps = int(self.IMAGEN_DELAY_S)
            for _ in range(imagen_steps):
                await asyncio.sleep(1.0)
                if self._closed:
                    return
                await self._emit_tone()

            # --- Phase 2: Imagen result arrives ------------------------------
            await self._events.put({
                "type": "media.image.created",
                "scene_id": "scene-1",
                "media_type": "image",
                "url": "mock://imagen/scene-1.png",
                "width": 1024,
                "height": 1024,
                "payload_size_bytes": 51200,
                "_mock_payload": "x" * 50000,
            })
            await self._events.put({
                "text": "Your blue robot is ready! Now let's make it move...",
            })

            # --- Phase 3: Veo delay (up to 30 s) ----------------------------
            veo_steps = int(self.VEO_DELAY_S - self.IMAGEN_DELAY_S)
            for i in range(veo_steps):
                await asyncio.sleep(1.0)
                if self._closed:
                    return
                if i % 3 == 0:
                    await self._emit_tone(duration_ms=200)

            # --- Phase 4: media_delayed signal (30 s mark) -------------------
            await self._events.put({
                "type": "media_delayed",
                "scene_id": "scene-2",
                "elapsed_seconds": 30,
            })
            await self._events.put({
                "text": "This is a big magic trick — it's taking a bit longer!",
            })

            # Continue tones for post-delay period
            post_steps = int(self.POST_DELAY_AUDIO_S)
            for _ in range(post_steps):
                await asyncio.sleep(1.0)
                if self._closed:
                    return
                await self._emit_tone(duration_ms=100)

            # --- Phase 5: Veo result finally arrives -------------------------
            await self._events.put({
                "type": "media.video.created",
                "scene_id": "scene-2",
                "media_type": "video",
                "url": "mock://veo/scene-2.mp4",
                "duration_seconds": 8,
                "payload_size_bytes": 102400,
                "_mock_payload": "x" * 100000,
            })
            await self._events.put({
                "text": "Look! Your robot is moving now!",
            })
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

async def _mock_stream_factory(*, model: str, session_id: str):
    _ = model, session_id
    return MockGeminiLiveStream()


async def _pilot_stream_factory(*, model: str, session_id: str):
    _ = model, session_id
    return PilotMockGeminiLiveStream()


def get_live_model() -> str:
    load_env_once()
    return os.getenv("DEMO_AGENT_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")


def build_live_client(*, persona_data: dict | None = None) -> GeminiLiveClient:
    load_env_once()
    live_mode = os.getenv("ANIMISM_LIVE_MODE", "adk").lower()
    if live_mode == "pilot":
        return GeminiLiveClient(model=get_live_model(), stream_factory=_pilot_stream_factory, persona_data=persona_data)
    if live_mode == "mock":
        return GeminiLiveClient(model=get_live_model(), stream_factory=_mock_stream_factory, persona_data=persona_data)
    return GeminiLiveClient(model=get_live_model(), persona_data=persona_data)
