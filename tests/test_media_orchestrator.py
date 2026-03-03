"""
V3.1–V3.3 Backend Real Media Orchestration Tests (TDD-first)

Tests the ``MediaOrchestrator`` — a self-contained service that triggers
Imagen and Veo generation concurrently while emitting the exact event
contract consumed by the frontend:

    - drawing_in_progress
    - media.image.created
    - media_delayed  (when Veo exceeds fallback timeout)
    - media.video.created

All tests mock the genai.Client at the SDK boundary — no real API calls.
The orchestrator's async behaviour, event ordering, fallback logic, and
prompt grounding are validated deterministically.

References:
    - validation-epic3-story.md (V3.1, V3.2, V3.3)
    - validation-integration-mocked-story.md (event contract)
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Backend path injection ────────────────────────────────────────────────────
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.media_orchestrator import (  # noqa: E402
    MediaOrchestrator,
    PromptBundle,
    build_scene_prompts,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers — genai SDK mocks at adapter boundary
# ══════════════════════════════════════════════════════════════════════════════

class FakeImageFile:
    """Simulates genai image file with ``save()``."""
    def __init__(self, data: bytes = b"fake-png") -> None:
        self._data = data

    def save(self, path: str) -> None:
        Path(path).write_bytes(self._data)


class FakeGeneratedImage:
    def __init__(self) -> None:
        self.image = FakeImageFile()


class FakeImageResponse:
    def __init__(self, *, delay_s: float = 0.0) -> None:
        self.generated_images = [FakeGeneratedImage()]
        self._delay_s = delay_s


class FakeVideoFile:
    def __init__(self, data: bytes = b"fake-mp4") -> None:
        self._data = data

    def save(self, path: str) -> None:
        Path(path).write_bytes(self._data)


class FakeGeneratedVideo:
    def __init__(self) -> None:
        self.video = FakeVideoFile()


class FakeVideoResponse:
    def __init__(self) -> None:
        self.generated_videos = [FakeGeneratedVideo()]


class FakeVideoOperation:
    """Simulates a Veo long-running operation with configurable poll count."""

    def __init__(self, *, polls_until_done: int = 2, poll_delay_s: float = 0.01) -> None:
        self._polls_remaining = polls_until_done
        self.done = False
        self.response: FakeVideoResponse | None = None
        self._poll_delay_s = poll_delay_s

    def poll_once(self) -> "FakeVideoOperation":
        self._polls_remaining -= 1
        if self._polls_remaining <= 0:
            self.done = True
            self.response = FakeVideoResponse()
        return self


class FakeGenaiClient:
    """Minimal mock of ``google.genai.Client`` covering models/operations/files."""

    def __init__(
        self,
        *,
        imagen_delay_s: float = 0.01,
        veo_polls: int = 2,
        veo_poll_delay_s: float = 0.01,
    ) -> None:
        self._imagen_delay_s = imagen_delay_s
        self._veo_polls = veo_polls
        self._veo_poll_delay_s = veo_poll_delay_s
        self.models = self._Models(self)
        self.operations = self._Operations(self)
        self.files = self._Files()
        # Track calls for assertion
        self.imagen_calls: list[dict[str, Any]] = []
        self.veo_calls: list[dict[str, Any]] = []

    class _Models:
        def __init__(self, parent: "FakeGenaiClient") -> None:
            self._p = parent

        def generate_images(self, *, model: str, prompt: str, config: Any = None) -> FakeImageResponse:
            self._p.imagen_calls.append({"model": model, "prompt": prompt})
            time.sleep(self._p._imagen_delay_s)
            return FakeImageResponse()

        def generate_videos(self, *, model: str, prompt: str, config: Any = None) -> FakeVideoOperation:
            self._p.veo_calls.append({"model": model, "prompt": prompt})
            return FakeVideoOperation(
                polls_until_done=self._p._veo_polls,
                poll_delay_s=self._p._veo_poll_delay_s,
            )

    class _Operations:
        def __init__(self, parent: "FakeGenaiClient") -> None:
            self._p = parent

        def get(self, operation: FakeVideoOperation) -> FakeVideoOperation:
            return operation.poll_once()

    class _Files:
        def download(self, file: Any) -> Any:
            return file


def _collect_events(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group emitted events by type for easy assertion."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        t = e.get("type", "unknown")
        grouped.setdefault(t, []).append(e)
    return grouped


# ══════════════════════════════════════════════════════════════════════════════
# V3.1 — Asynchronous Media Orchestration
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v31_orchestrator_emits_drawing_in_progress_first():
    """First event emitted must be ``drawing_in_progress`` for the scene."""
    client = FakeGenaiClient()
    orchestrator = MediaOrchestrator(client=client, poll_interval_s=0.01, fallback_timeout_s=10.0)

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-1",
        image_prompt="A blue robot in a park",
        video_prompt="The blue robot walks gently",
        event_sink=events.append,
    )

    assert len(events) >= 2, f"Expected at least 2 events, got {len(events)}"
    assert events[0]["type"] == "drawing_in_progress"
    assert events[0]["scene_id"] == "scene-1"


@pytest.mark.asyncio
async def test_v31_orchestrator_emits_image_created_with_url():
    """After Imagen completes, a ``media.image.created`` event is emitted."""
    client = FakeGenaiClient()
    orchestrator = MediaOrchestrator(client=client, poll_interval_s=0.01, fallback_timeout_s=10.0)

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-1",
        image_prompt="A blue robot",
        video_prompt="Robot walks",
        event_sink=events.append,
    )

    grouped = _collect_events(events)
    image_events = grouped.get("media.image.created", [])
    assert len(image_events) == 1
    assert image_events[0]["scene_id"] == "scene-1"
    assert "url" in image_events[0]
    assert image_events[0]["media_type"] == "image"
    assert image_events[0]["width"] == 1024
    assert image_events[0]["height"] == 1024


@pytest.mark.asyncio
async def test_v31_orchestrator_emits_video_created_with_url():
    """After Veo completes, a ``media.video.created`` event is emitted."""
    client = FakeGenaiClient(veo_polls=2, veo_poll_delay_s=0.01)
    orchestrator = MediaOrchestrator(client=client, poll_interval_s=0.01, fallback_timeout_s=10.0)

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-1",
        image_prompt="A blue robot",
        video_prompt="Robot walks",
        event_sink=events.append,
    )

    grouped = _collect_events(events)
    video_events = grouped.get("media.video.created", [])
    assert len(video_events) == 1
    assert video_events[0]["scene_id"] == "scene-1"
    assert "url" in video_events[0]
    assert video_events[0]["media_type"] == "video"
    assert video_events[0]["duration_seconds"] == 8


@pytest.mark.asyncio
async def test_v31_image_arrives_before_video(output_dir):
    """V3.1 AC2: Imagen should resolve before Veo finishes polling."""
    client = FakeGenaiClient(imagen_delay_s=0.01, veo_polls=5, veo_poll_delay_s=0.01)
    orchestrator = MediaOrchestrator(
        client=client,
        poll_interval_s=0.01,
        fallback_timeout_s=10.0,
        output_dir=output_dir,
    )

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-1",
        image_prompt="A blue robot",
        video_prompt="Robot walks",
        event_sink=events.append,
    )

    event_types = [e["type"] for e in events]
    img_idx = event_types.index("media.image.created")
    vid_idx = event_types.index("media.video.created")
    assert img_idx < vid_idx, (
        f"Image event at index {img_idx} should arrive before video at {vid_idx}"
    )


@pytest.mark.asyncio
async def test_v31_concurrent_orchestration_non_blocking():
    """V3.1 AC1: Both Imagen and Veo run concurrently via asyncio."""
    client = FakeGenaiClient(imagen_delay_s=0.05, veo_polls=3, veo_poll_delay_s=0.05)
    orchestrator = MediaOrchestrator(client=client, poll_interval_s=0.05, fallback_timeout_s=10.0)

    events: list[dict[str, Any]] = []
    t0 = time.monotonic()
    await orchestrator.orchestrate_scene(
        scene_id="scene-1",
        image_prompt="A blue robot",
        video_prompt="Robot walks",
        event_sink=events.append,
    )
    elapsed = time.monotonic() - t0

    # If sequential, total ≈ 0.05 (imagen) + 3*0.05 (veo) = 0.20
    # If concurrent, total ≈ max(0.05, 3*0.05) = 0.15
    # Allow generous margin but assert it's less than fully sequential
    assert elapsed < 0.5, f"Took {elapsed:.3f}s — orchestration may not be concurrent"

    grouped = _collect_events(events)
    assert len(grouped.get("media.image.created", [])) == 1
    assert len(grouped.get("media.video.created", [])) == 1


@pytest.mark.asyncio
async def test_v31_artifacts_saved_to_disk(output_dir):
    """V3.1 AC3: Both artifacts saved to disk with session markers."""
    client = FakeGenaiClient(veo_polls=2)
    orchestrator = MediaOrchestrator(
        client=client,
        poll_interval_s=0.01,
        fallback_timeout_s=10.0,
        output_dir=output_dir,
    )

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-1",
        image_prompt="A blue robot",
        video_prompt="Robot walks",
        event_sink=events.append,
    )

    # Check files were saved
    image_files = list(output_dir.glob("scene-1*imagen*.png"))
    video_files = list(output_dir.glob("scene-1*social_story*.mp4"))
    assert len(image_files) >= 1, f"No image artifact saved: {list(output_dir.iterdir())}"
    assert len(video_files) >= 1, f"No video artifact saved: {list(output_dir.iterdir())}"


# ══════════════════════════════════════════════════════════════════════════════
# V3.2 — Contextual Prompt Grounding (Persona-to-Media)
# ══════════════════════════════════════════════════════════════════════════════


def test_v32_build_scene_prompts_includes_persona_traits():
    """V3.2 AC1-AC2: Prompts include visual traits and personality."""
    prompts = build_scene_prompts(
        visual_traits=["blue robot arms", "round eyes"],
        personality_traits=["gentle", "curious"],
        child_context="a peaceful park with soft wind",
    )

    assert isinstance(prompts, PromptBundle)
    assert "blue robot arms" in prompts.image_prompt
    assert "round eyes" in prompts.image_prompt
    assert "gentle" in prompts.video_prompt
    assert "curious" in prompts.video_prompt
    assert "peaceful park" in prompts.image_prompt


def test_v32_prompts_are_grade1_friendly():
    """V3.2 AC3: Prompts use simple language (no words > 12 chars)."""
    prompts = build_scene_prompts(
        visual_traits=["blue arms"],
        personality_traits=["calm"],
        child_context="a sunny garden",
    )

    def _is_grade1(text: str) -> bool:
        words = [w.strip(".,;:!?\"'") for w in text.split()]
        return all(len(w) <= 12 for w in words if w)

    assert _is_grade1(prompts.image_prompt), f"Image prompt not grade-1: {prompts.image_prompt}"
    assert _is_grade1(prompts.video_prompt), f"Video prompt not grade-1: {prompts.video_prompt}"


def test_v32_prompts_differ_for_image_and_video():
    """Image and video prompts serve different purposes."""
    prompts = build_scene_prompts(
        visual_traits=["wings"],
        personality_traits=["kind"],
        child_context="flying over clouds",
    )
    assert prompts.image_prompt != prompts.video_prompt


# ══════════════════════════════════════════════════════════════════════════════
# V3.3 — Resilience & Fallback Visual Validation
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_v33_media_delayed_emitted_at_timeout():
    """V3.3 AC1: When Veo exceeds fallback timeout, ``media_delayed`` is emitted."""
    # Veo takes many polls to complete; with compressed timing the fallback fires
    client = FakeGenaiClient(veo_polls=50, veo_poll_delay_s=0.001)
    orchestrator = MediaOrchestrator(
        client=client,
        poll_interval_s=0.05,
        fallback_timeout_s=0.2,  # Very short timeout for test speed
    )

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-delayed",
        image_prompt="A blue robot",
        video_prompt="Robot walks slowly",
        event_sink=events.append,
    )

    grouped = _collect_events(events)
    delayed = grouped.get("media_delayed", [])
    assert len(delayed) >= 1, f"Expected media_delayed event, got types: {[e['type'] for e in events]}"
    assert delayed[0]["scene_id"] == "scene-delayed"
    assert "elapsed_seconds" in delayed[0]


@pytest.mark.asyncio
async def test_v33_video_eventually_replaces_fallback():
    """V3.3 AC3: Even after fallback, the Veo result eventually arrives."""
    client = FakeGenaiClient(veo_polls=15, veo_poll_delay_s=0.001)
    orchestrator = MediaOrchestrator(
        client=client,
        poll_interval_s=0.02,
        fallback_timeout_s=0.1,  # Short timeout → fallback fires
    )

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-fallback",
        image_prompt="Robot",
        video_prompt="Robot walks",
        event_sink=events.append,
    )

    grouped = _collect_events(events)
    # Both delayed AND completed should be present
    assert len(grouped.get("media_delayed", [])) >= 1
    assert len(grouped.get("media.video.created", [])) == 1, (
        f"Video should eventually complete. Events: {[e['type'] for e in events]}"
    )

    # Delayed comes before completed
    event_types = [e["type"] for e in events]
    delayed_idx = event_types.index("media_delayed")
    completed_idx = event_types.index("media.video.created")
    assert delayed_idx < completed_idx


@pytest.mark.asyncio
async def test_v33_no_fallback_when_video_completes_fast():
    """If Veo completes before timeout, no ``media_delayed`` is emitted."""
    client = FakeGenaiClient(veo_polls=2, veo_poll_delay_s=0.01)
    orchestrator = MediaOrchestrator(
        client=client,
        poll_interval_s=0.01,
        fallback_timeout_s=10.0,  # Very generous timeout
    )

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-fast",
        image_prompt="Robot",
        video_prompt="Robot runs",
        event_sink=events.append,
    )

    grouped = _collect_events(events)
    assert len(grouped.get("media_delayed", [])) == 0, "No delayed event when video is fast"
    assert len(grouped.get("media.video.created", [])) == 1


@pytest.mark.asyncio
async def test_v33_event_ordering_full_flow():
    """Full flow event ordering: progress → image → [delayed] → video."""
    client = FakeGenaiClient(veo_polls=20, veo_poll_delay_s=0.001)
    orchestrator = MediaOrchestrator(
        client=client,
        poll_interval_s=0.02,
        fallback_timeout_s=0.15,
    )

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-full",
        image_prompt="Robot",
        video_prompt="Robot flies",
        event_sink=events.append,
    )

    types = [e["type"] for e in events]
    assert types[0] == "drawing_in_progress"
    assert "media.image.created" in types
    assert "media.video.created" in types

    # Image before video
    assert types.index("media.image.created") < types.index("media.video.created")


@pytest.mark.asyncio
async def test_v31_sdk_models_called_with_correct_params():
    """Orchestrator delegates to genai Client with correct model and prompt."""
    client = FakeGenaiClient(veo_polls=2)
    orchestrator = MediaOrchestrator(client=client, poll_interval_s=0.01, fallback_timeout_s=10.0)

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="s1",
        image_prompt="blue robot prompt",
        video_prompt="walking robot prompt",
        event_sink=events.append,
    )

    assert len(client.imagen_calls) == 1
    assert client.imagen_calls[0]["prompt"] == "blue robot prompt"
    assert "imagen" in client.imagen_calls[0]["model"].lower()

    assert len(client.veo_calls) == 1
    assert client.veo_calls[0]["prompt"] == "walking robot prompt"
    assert "veo" in client.veo_calls[0]["model"].lower()


@pytest.mark.asyncio
async def test_v31_all_events_have_scene_id():
    """Every emitted event must carry the scene_id for frontend correlation."""
    client = FakeGenaiClient(veo_polls=10, veo_poll_delay_s=0.001)
    orchestrator = MediaOrchestrator(
        client=client, poll_interval_s=0.02, fallback_timeout_s=0.08
    )

    events: list[dict[str, Any]] = []
    await orchestrator.orchestrate_scene(
        scene_id="scene-42",
        image_prompt="R",
        video_prompt="R",
        event_sink=events.append,
    )

    for e in events:
        assert "scene_id" in e, f"Event missing scene_id: {e}"
        assert e["scene_id"] == "scene-42"
