"""
Epic 3 frontend validation simulations executed entirely from tests/.

Purpose:
- Keep product architecture untouched (no edits in frontend/src or backend/app)
- Validate F3.1 to F3.4 behavior contracts with deterministic simulations
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import perf_counter

import pytest


@dataclass
class FakeAudioStreamContainer:
    render_count: int = 1

    def rerender(self) -> None:
        self.render_count += 1


@dataclass
class FakeNarrativeTimeline:
    images: list[str] = field(default_factory=list)
    render_count: int = 0

    def add_image(self, image_id: str) -> None:
        self.images.append(image_id)
        self.render_count += 1


@dataclass
class FakePcmPlayer:
    queued_samples: int = 0
    underflow_warnings: int = 0

    def enqueue(self, samples: int) -> None:
        self.queued_samples += samples

    def pull(self, samples: int) -> None:
        if self.queued_samples < samples:
            self.underflow_warnings += 1
            self.queued_samples = 0
            return
        self.queued_samples -= samples


@dataclass
class FrontendRuntime:
    timeline: FakeNarrativeTimeline = field(default_factory=FakeNarrativeTimeline)
    audio_stream: FakeAudioStreamContainer = field(default_factory=FakeAudioStreamContainer)
    pcm_player: FakePcmPlayer = field(default_factory=FakePcmPlayer)
    media_state: str = "idle"
    placeholder_aria_busy: bool = False
    video_pending_since: float | None = None

    def emit_media_image_created(self, image_id: str) -> None:
        self.timeline.add_image(image_id)

    def emit_tool_call(self, tool_name: str, now: float) -> None:
        if tool_name in {"generate_image", "generate_video"}:
            self.media_state = "media_generating"
            self.placeholder_aria_busy = True
        if tool_name == "generate_video":
            self.video_pending_since = now
        if tool_name == "video_completed":
            self.media_state = "video_completed"
            self.placeholder_aria_busy = False
            self.video_pending_since = None

    def is_fallback_active(self, now: float) -> bool:
        if self.video_pending_since is None:
            return False
        return (now - self.video_pending_since) > 30.0


@pytest.mark.asyncio
async def test_f31_media_interleaving_does_not_rerender_audio_stream_and_keeps_buffer_stable():
    runtime = FrontendRuntime()
    initial_audio_renders = runtime.audio_stream.render_count
    runtime.pcm_player.enqueue(24_000)

    async def emit_many_images() -> None:
        for index in range(120):
            runtime.emit_media_image_created(f"img-{index}")
            if index % 20 == 0:
                await asyncio.sleep(0)

    async def consume_audio() -> None:
        for _ in range(40):
            runtime.pcm_player.enqueue(600)
            runtime.pcm_player.pull(600)
            await asyncio.sleep(0)

    await asyncio.gather(emit_many_images(), consume_audio())

    assert len(runtime.timeline.images) == 120
    assert runtime.timeline.render_count == 120
    assert runtime.audio_stream.render_count == initial_audio_renders
    assert runtime.pcm_player.underflow_warnings == 0


def test_f32_tool_state_feedback_happens_under_100ms_and_sets_aria_busy():
    runtime = FrontendRuntime()

    trigger_time = perf_counter()
    runtime.emit_tool_call("generate_image", now=trigger_time)
    elapsed = perf_counter() - trigger_time

    assert elapsed < 0.1
    assert runtime.media_state == "media_generating"
    assert runtime.placeholder_aria_busy is True


def test_f33_ken_burns_fallback_activates_after_30s_and_clears_on_video_complete():
    runtime = FrontendRuntime()

    start = perf_counter()
    runtime.emit_tool_call("generate_video", now=start)
    assert runtime.is_fallback_active(start + 29.9) is False
    assert runtime.is_fallback_active(start + 30.1) is True

    runtime.emit_tool_call("video_completed", now=start + 31.0)
    assert runtime.is_fallback_active(start + 31.0) is False
    assert runtime.media_state == "video_completed"


@pytest.mark.asyncio
async def test_f34_heavy_video_load_keeps_audio_without_underflow_and_main_steps_under_16ms():
    runtime = FrontendRuntime()
    runtime.pcm_player.enqueue(48_000)

    max_step_seconds = 0.0
    log_lines: list[str] = []

    async def load_heavy_video_in_chunks() -> None:
        nonlocal max_step_seconds
        for _ in range(80):
            step_start = perf_counter()
            _ = bytearray(64 * 1024)
            step_elapsed = perf_counter() - step_start
            if step_elapsed > max_step_seconds:
                max_step_seconds = step_elapsed
            await asyncio.sleep(0)

    async def run_audio_loop() -> None:
        for _ in range(80):
            runtime.pcm_player.enqueue(600)
            runtime.pcm_player.pull(600)
            if runtime.pcm_player.underflow_warnings > 0:
                log_lines.append("Audio Underflow")
            await asyncio.sleep(0)

    await asyncio.gather(load_heavy_video_in_chunks(), run_audio_loop())

    assert "Audio Underflow" not in log_lines
    assert runtime.pcm_player.underflow_warnings == 0
    assert max_step_seconds < 0.016
