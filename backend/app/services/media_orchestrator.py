"""MediaOrchestrator — async Imagen + Veo generation with fallback logic.

Self-contained service that orchestrates multimodal media generation for a
single "scene" within the storytelling flow.  Designed to run alongside the
live-audio conversation without blocking it.

Key responsibilities:
    1. Trigger Imagen first, then Veo with optional image reference.
    2. Emit events matching the frontend's established contract:
       - ``drawing_in_progress`` — generation started
       - ``media.image.created`` — Imagen result ready (includes URL/path)
       - ``media_delayed``       — Veo exceeded fallback timeout (NFR12)
       - ``media.video.created`` — Veo result ready (includes URL/path)
    3. Poll the Veo long-running operation with configurable interval.
    4. Optionally save artifacts to disk with session markers.
    5. Remain fully testable via injected ``genai.Client`` (mock or real).

No dependency on bridge, audio, or WebSocket code.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.services import debug_tracer
from app.services.asset_store import AssetStore

logger = logging.getLogger(__name__)

# Default model identifiers (match existing test fixtures)
IMAGEN_MODEL = "imagen-4.0-generate-001"
VEO_MODEL = "veo-3.0-fast-generate-001"
DEFAULT_VEO_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_VEO_FALLBACK_TIMEOUT_SECONDS = 10.0

# Frontend media contract defaults (Epic 3 parser requirements)
DEFAULT_IMAGE_WIDTH = 1024
DEFAULT_IMAGE_HEIGHT = 1024
DEFAULT_VIDEO_DURATION_SECONDS = 8


# ── Prompt Grounding (V3.2) ──────────────────────────────────────────────────

@dataclass(frozen=True)
class PromptBundle:
    """Paired image + video prompts grounded in persona traits."""

    image_prompt: str
    video_prompt: str


def build_scene_prompts(
    *,
    visual_traits: list[str] | tuple[str, ...],
    personality_traits: list[str] | tuple[str, ...],
    child_context: str,
) -> PromptBundle:
    """Build persona-grounded prompts for Imagen and Veo (V3.2).

    Language is kept at Grade-1 level (no words > 12 chars) to comply
    with NFR10 / therapeutic safety guidelines.
    """
    visual = ", ".join(visual_traits)
    personality = ", ".join(personality_traits)

    image_prompt = (
        "A gentle story picture for a child. "
        f"Traits: {visual}. "
        f"Mood: {personality}. "
        f"Scene: {child_context}. "
        "Use bright, safe, calming colors."
    )
    video_prompt = (
        "A short calm story video. "
        f"Same traits: {visual}. "
        f"Same mood: {personality}. "
        f"Story: {child_context}. "
        "Show calm motion and a kind ending."
    )
    return PromptBundle(image_prompt=image_prompt, video_prompt=video_prompt)


# ── Event type alias ─────────────────────────────────────────────────────────

MediaEvent = dict[str, Any]
EventSink = Callable[[MediaEvent], Any]


# ── MediaOrchestrator ────────────────────────────────────────────────────────

class MediaOrchestrator:
    """Orchestrates sequential Imagen -> Veo generation for a scene.

    Parameters
    ----------
    client:
        A ``google.genai.Client`` (or compatible mock) with
        ``client.models.generate_images``, ``client.models.generate_videos``,
        ``client.operations.get``, and ``client.files.download``.
    poll_interval_s:
        Seconds between Veo polling attempts.
    fallback_timeout_s:
        Seconds after which a ``media_delayed`` event is emitted (NFR12).
    output_dir:
        If set, artifacts are saved to this directory.
    imagen_model:
        Model identifier for Imagen.
    veo_model:
        Model identifier for Veo.
    """

    def __init__(
        self,
        client: Any,
        *,
        poll_interval_s: float = DEFAULT_VEO_POLL_INTERVAL_SECONDS,
        fallback_timeout_s: float = DEFAULT_VEO_FALLBACK_TIMEOUT_SECONDS,
        output_dir: Path | None = None,
        asset_store: AssetStore | None = None,
        imagen_model: str = IMAGEN_MODEL,
        veo_model: str = VEO_MODEL,
    ) -> None:
        self._client = client
        self._poll_interval_s = poll_interval_s
        self._fallback_timeout_s = fallback_timeout_s
        self._output_dir = output_dir
        self._asset_store = asset_store
        self._imagen_model = imagen_model
        self._veo_model = veo_model

    # ── Public API ───────────────────────────────────────────────────────

    async def orchestrate_scene(
        self,
        *,
        scene_id: str,
        image_prompt: str,
        video_prompt: str,
        event_sink: EventSink,
    ) -> None:
        """Run the full Imagen -> Veo pipeline for a scene.

        Events are pushed to ``event_sink`` as they happen. The function
        returns only after both tasks complete (or are handled).
        """
        debug_tracer.log_debug(
            event_type="scene_orchestration_started",
            source="orchestrator",
            scene_id=scene_id,
        )
        imagen_image = await self.generate_image_only(
            scene_id=scene_id,
            image_prompt=image_prompt,
            event_sink=event_sink,
        )
        await self.generate_video_only(
            scene_id=scene_id,
            video_prompt=video_prompt,
            event_sink=event_sink,
            imagen_image=imagen_image,
        )

    async def generate_image_only(
        self,
        *,
        scene_id: str,
        image_prompt: str,
        event_sink: EventSink,
    ) -> Any | None:
        """Generate only the Imagen step for a scene and return the image."""
        await self._emit(event_sink, {
            "type": "drawing_in_progress",
            "scene_id": scene_id,
        })
        return await self._generate_image(scene_id, image_prompt, event_sink)

    async def generate_video_only(
        self,
        *,
        scene_id: str,
        video_prompt: str,
        event_sink: EventSink,
        imagen_image: Any | None = None,
    ) -> None:
        """Generate only the Veo step for a scene."""
        await self._generate_video(
            scene_id,
            video_prompt,
            event_sink,
            imagen_image=imagen_image,
        )

    # ── Imagen generation ────────────────────────────────────────────────

    async def _generate_image(
        self,
        scene_id: str,
        prompt: str,
        event_sink: EventSink,
    ) -> Any | None:
        """Call Imagen, emit ``media.image.created``, and return generated image."""
        try:
            response = await asyncio.to_thread(
                self._client.models.generate_images,
                model=self._imagen_model,
                prompt=prompt,
            )
        except Exception:
            logger.exception("Imagen generation failed for scene %s", scene_id)
            return None

        if not response.generated_images:
            logger.warning("Imagen returned no images for scene %s", scene_id)
            return None

        image = response.generated_images[0].image

        # Resolve URL — prefer AssetStore (returns HTTP URL), then output_dir, then fallback
        url = f"asset://imagen/{scene_id}.png"
        if self._asset_store is not None:
            try:
                url = await self._asset_store.save_image(scene_id, image.save)
            except Exception:
                logger.exception("AssetStore image save failed for scene %s", scene_id)
        elif self._output_dir:
            artifact_path = self._output_dir / f"{scene_id}_imagen_still.png"
            try:
                await asyncio.to_thread(image.save, str(artifact_path))
                url = str(artifact_path)
            except Exception:
                logger.exception("Disk image save failed for scene %s", scene_id)

        await self._emit(event_sink, {
            "type": "media.image.created",
            "scene_id": scene_id,
            "media_type": "image",
            "url": url,
            "width": DEFAULT_IMAGE_WIDTH,
            "height": DEFAULT_IMAGE_HEIGHT,
        })
        return image

    # ── Veo generation with polling + fallback ───────────────────────────

    async def _generate_video(
        self,
        scene_id: str,
        prompt: str,
        event_sink: EventSink,
        *,
        imagen_image: Any | None = None,
    ) -> None:
        """Start Veo, poll with fallback timeout, emit events."""
        video_start_time = time.monotonic()
        self._log_video_phase(
            event_type="video_generation_started",
            scene_id=scene_id,
            start_time=video_start_time,
        )
        try:
            operation = await asyncio.to_thread(
                self._client.models.generate_videos,
                model=self._veo_model,
                prompt=prompt,
                image=imagen_image,
            )
        except Exception:
            logger.exception("Veo generation start failed for scene %s", scene_id)
            return

        self._log_video_phase(
            event_type="veo_operation_created",
            scene_id=scene_id,
            start_time=video_start_time,
            poll_interval_s=self._poll_interval_s,
            fallback_timeout_s=self._fallback_timeout_s,
        )

        start_time = video_start_time
        fallback_emitted = False
        poll_count = 0

        self._log_video_phase(
            event_type="veo_polling_started",
            scene_id=scene_id,
            start_time=video_start_time,
            poll_interval_s=self._poll_interval_s,
        )

        while not operation.done:
            await asyncio.sleep(self._poll_interval_s)
            poll_count += 1

            elapsed = time.monotonic() - start_time

            # Emit fallback signal once when timeout is exceeded
            if not fallback_emitted and elapsed >= self._fallback_timeout_s:
                fallback_emitted = True
                await self._emit(event_sink, {
                    "type": "media_delayed",
                    "scene_id": scene_id,
                    "elapsed_seconds": round(elapsed, 1),
                })
                self._log_video_phase(
                    event_type="veo_fallback_emitted",
                    scene_id=scene_id,
                    start_time=video_start_time,
                    elapsed_s=round(elapsed, 3),
                    poll_count=poll_count,
                )
                logger.info(
                    "Veo fallback timeout for scene %s at %.1fs",
                    scene_id, elapsed,
                )

            # Poll the operation
            try:
                operation = await asyncio.to_thread(
                    self._client.operations.get,
                    operation,
                )
            except Exception:
                logger.exception("Veo poll failed for scene %s", scene_id)
                return

        # Operation complete — extract and save the video
        if not operation.response or not operation.response.generated_videos:
            logger.warning("Veo completed but no videos for scene %s", scene_id)
            return

        generated_video = operation.response.generated_videos[0]

        # Download the file
        try:
            await asyncio.to_thread(
                self._client.files.download,
                file=generated_video.video,
            )
        except Exception:
            logger.exception("Veo download failed for scene %s", scene_id)
            return

        video = generated_video.video

        # Resolve URL — prefer AssetStore (returns HTTP URL), then output_dir, then fallback
        url = f"asset://veo/{scene_id}.mp4"
        if self._asset_store is not None:
            try:
                url = await self._asset_store.save_video(scene_id, video.save)
            except Exception:
                logger.exception("AssetStore video save failed for scene %s", scene_id)
        elif self._output_dir:
            artifact_path = self._output_dir / f"{scene_id}_social_story.mp4"
            try:
                await asyncio.to_thread(video.save, str(artifact_path))
                url = str(artifact_path)
            except Exception:
                logger.exception("Disk video save failed for scene %s", scene_id)

        await self._emit(event_sink, {
            "type": "media.video.created",
            "scene_id": scene_id,
            "media_type": "video",
            "url": url,
            "duration_seconds": DEFAULT_VIDEO_DURATION_SECONDS,
        })
        self._log_video_phase(
            event_type="veo_video_ready_emitted",
            scene_id=scene_id,
            start_time=video_start_time,
            poll_count=poll_count,
            url=url,
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _log_video_phase(
        *,
        event_type: str,
        scene_id: str,
        start_time: float,
        elapsed_s: float | None = None,
        **extra: Any,
    ) -> None:
        if elapsed_s is None:
            elapsed_s = round(max(time.monotonic() - start_time, 0.0), 3)
        debug_tracer.log_debug(
            event_type=event_type,
            source="orchestrator",
            scene_id=scene_id,
            elapsed_s=elapsed_s,
            **extra,
        )

    @staticmethod
    async def _emit(sink: EventSink, event: MediaEvent) -> None:
        """Push an event to the sink (supports sync and async callables)."""
        debug_tracer.log_debug(
            event_type="media_event_emitted",
            source="orchestrator",
            scene_id=event.get("scene_id"),
            event_kind=event.get("type"),
        )
        result = sink(event)
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            await result
