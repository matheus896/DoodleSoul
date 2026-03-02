"""
Epic 3 validation tests for asynchronous multimodal orchestration.

These tests intentionally run as deterministic simulations (no external API calls)
to validate orchestration behavior before wiring into production runtime.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import Any

import pytest


IMAGEN_MODEL = "imagen-4.0-generate-001"
VEO_MODEL = "veo-3.0-fast-generate-001"

POLL_INTERVAL_SECONDS = 5
FALLBACK_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Persona:
    session_id: str
    visual_traits: tuple[str, ...]
    personality_traits: tuple[str, ...]
    child_context: str


@dataclass(frozen=True)
class PromptBundle:
    image_prompt: str
    video_prompt: str


def build_persona_grounded_prompts(persona: Persona) -> PromptBundle:
    visual = ", ".join(persona.visual_traits)
    personality = ", ".join(persona.personality_traits)
    image_prompt = (
        "A gentle social-story illustration for a child. "
        f"Character traits: {visual}. "
        f"Personality: {personality}. "
        f"Scene: {persona.child_context}. "
        "Use bright, safe, calming colors."
    )
    video_prompt = (
        "A short therapeutic social-story video. "
        f"Same character traits: {visual}. "
        f"Same personality: {personality}. "
        f"Narrative context: {persona.child_context}. "
        "Show calm movement and a friendly ending."
    )
    return PromptBundle(image_prompt=image_prompt, video_prompt=video_prompt)


def _is_grade1_friendly(text: str) -> bool:
    words = [word.strip(".,:;!?\"") for word in text.split()]
    meaningful_words = [word for word in words if word]
    long_words = [word for word in meaningful_words if len(word) > 12]
    return len(long_words) == 0


class _FakeImageFile:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def save(self, output_path: str) -> None:
        Path(output_path).write_bytes(self.payload)


class _FakeGeneratedImage:
    def __init__(self, payload: bytes) -> None:
        self.image = _FakeImageFile(payload)


class _FakeImageResponse:
    def __init__(self, payload: bytes) -> None:
        self.generated_images = [_FakeGeneratedImage(payload)]


class _FakeVideoFile:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def save(self, output_path: str) -> None:
        Path(output_path).write_bytes(self.payload)


class _FakeGeneratedVideo:
    def __init__(self, payload: bytes) -> None:
        self.video = _FakeVideoFile(payload)


class _FakeVideoResponse:
    def __init__(self, payload: bytes) -> None:
        self.generated_videos = [_FakeGeneratedVideo(payload)]


class _FakeVideoOperation:
    def __init__(self, polls_until_done: int, payload: bytes) -> None:
        self._polls_until_done = polls_until_done
        self._payload = payload
        self.done = False
        self.response: _FakeVideoResponse | None = None

    def poll_once(self) -> "_FakeVideoOperation":
        if self.done:
            return self

        self._polls_until_done -= 1
        if self._polls_until_done <= 0:
            self.done = True
            self.response = _FakeVideoResponse(self._payload)
        return self


class _FakeModels:
    def generate_images(self, *args: Any, **kwargs: Any) -> _FakeImageResponse:
        del args, kwargs
        sleep(0.05)
        return _FakeImageResponse(payload=b"fake-imagen-bytes")

    def generate_videos(self, *args: Any, **kwargs: Any) -> _FakeVideoOperation:
        del args, kwargs
        sleep(0.15)
        return _FakeVideoOperation(polls_until_done=8, payload=b"fake-veo-bytes")


class _FakeOperations:
    def get(self, operation: _FakeVideoOperation) -> _FakeVideoOperation:
        return operation.poll_once()


class _FakeFiles:
    def download(self, file: _FakeVideoFile) -> _FakeVideoFile:
        return file


class _FakeClient:
    def __init__(self) -> None:
        self.models = _FakeModels()
        self.operations = _FakeOperations()
        self.files = _FakeFiles()


async def _generate_imagen_still(
    *,
    client: _FakeClient,
    output_dir: Path,
    prompt: str,
    session_marker: str,
) -> Path:
    response = await asyncio.to_thread(
        client.models.generate_images,
        model=IMAGEN_MODEL,
        prompt=prompt,
    )
    output_path = output_dir / f"{session_marker}_imagen_still.png"
    response.generated_images[0].image.save(str(output_path))
    return output_path


async def _start_veo_generation(
    *,
    client: _FakeClient,
    prompt: str,
) -> _FakeVideoOperation:
    return await asyncio.to_thread(
        client.models.generate_videos,
        model=VEO_MODEL,
        prompt=prompt,
    )


def _poll_video_until_complete(
    *,
    client: _FakeClient,
    operation: _FakeVideoOperation,
    output_dir: Path,
    session_marker: str,
    poll_interval_seconds: int,
) -> tuple[Path, int]:
    elapsed_seconds = 0
    current = operation
    while not current.done:
        current = client.operations.get(current)
        elapsed_seconds += poll_interval_seconds

    assert current.response is not None
    generated_video = current.response.generated_videos[0]
    client.files.download(file=generated_video.video)

    video_path = output_dir / f"{session_marker}_social_story.mp4"
    generated_video.video.save(str(video_path))
    return video_path, elapsed_seconds


def _persona_fixture() -> Persona:
    return Persona(
        session_id="epic3-session-001",
        visual_traits=("blue robot arms", "round eyes"),
        personality_traits=("gentle", "curious"),
        child_context="a peaceful park with soft wind",
    )


@pytest.mark.asyncio
async def test_v31_async_orchestration_runs_imagen_and_veo_without_blocking(output_dir):
    persona = _persona_fixture()
    prompts = build_persona_grounded_prompts(persona)
    client = _FakeClient()

    start = perf_counter()
    image_task = _generate_imagen_still(
        client=client,
        output_dir=output_dir,
        prompt=prompts.image_prompt,
        session_marker=persona.session_id,
    )
    video_task = _start_veo_generation(client=client, prompt=prompts.video_prompt)

    image_path, video_operation = await asyncio.gather(image_task, video_task)
    gather_elapsed = perf_counter() - start

    assert gather_elapsed < 5, "Imagen still should be ready within a short setup window"
    assert image_path.exists(), "Imagen still artifact should be saved to tests/output"
    assert image_path.stat().st_size > 0
    assert not video_operation.done, "Veo operation should continue polling after image is ready"

    video_path, simulated_elapsed = _poll_video_until_complete(
        client=client,
        operation=video_operation,
        output_dir=output_dir,
        session_marker=persona.session_id,
        poll_interval_seconds=POLL_INTERVAL_SECONDS,
    )

    assert 30 <= simulated_elapsed <= 60
    assert video_path.exists(), "Veo artifact should be saved after polling completes"
    assert video_path.stat().st_size > 0


def test_v32_prompt_grounding_uses_persona_traits_and_grade1_language():
    persona = _persona_fixture()
    prompts = build_persona_grounded_prompts(persona)

    assert "blue robot arms" in prompts.image_prompt
    assert "gentle" in prompts.video_prompt
    assert "peaceful park" in prompts.image_prompt

    assert _is_grade1_friendly(prompts.image_prompt)
    assert _is_grade1_friendly(prompts.video_prompt)


def test_v33_timeout_triggers_fallback_still_then_video_replaces_it(output_dir):
    persona = _persona_fixture()
    prompts = build_persona_grounded_prompts(persona)
    client = _FakeClient()

    operation = _FakeVideoOperation(polls_until_done=10, payload=b"late-veo-video")
    elapsed_seconds = 0
    fallback_image_path: Path | None = None
    active_visual = "video_pending"

    while not operation.done:
        if elapsed_seconds >= FALLBACK_TIMEOUT_SECONDS and fallback_image_path is None:
            fallback_response = client.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=prompts.image_prompt,
            )
            fallback_image_path = output_dir / f"{persona.session_id}_fallback_still.png"
            fallback_response.generated_images[0].image.save(str(fallback_image_path))
            active_visual = "fallback_active"

        operation = client.operations.get(operation)
        elapsed_seconds += POLL_INTERVAL_SECONDS

    assert fallback_image_path is not None
    assert fallback_image_path.exists()
    assert active_visual == "fallback_active"

    assert operation.response is not None
    generated_video = operation.response.generated_videos[0]
    client.files.download(file=generated_video.video)
    final_video_path = output_dir / f"{persona.session_id}_fallback_replaced_by_video.mp4"
    generated_video.video.save(str(final_video_path))

    assert final_video_path.exists()
    assert final_video_path.stat().st_size > 0
