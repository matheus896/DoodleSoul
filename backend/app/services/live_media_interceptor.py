from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.config.env_loader import load_env_once
from app.services import debug_tracer
from app.services.asset_store import build_asset_store
from app.services.media_orchestrator import MediaOrchestrator, build_scene_prompts

logger = logging.getLogger(__name__)

_MEDIA_TOOLS = {"generate_image", "generate_video"}


class MediaOrchestratorLike(Protocol):
    async def generate_image_only(
        self,
        *,
        scene_id: str,
        image_prompt: str,
        event_sink: Any,
    ) -> Any | None: ...

    async def generate_video_only(
        self,
        *,
        scene_id: str,
        video_prompt: str,
        event_sink: Any,
        imagen_image: Any | None = None,
    ) -> None: ...

    async def orchestrate_scene(
        self,
        *,
        scene_id: str,
        image_prompt: str,
        video_prompt: str,
        event_sink: Any,
    ) -> None: ...


def _extract_tool_call_payload(event: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
    if event.get("type") != "tool_call":
        return None

    tool = event.get("tool")
    if not isinstance(tool, str) or tool not in _MEDIA_TOOLS:
        return None

    raw_args_obj = event.get("args")
    raw_args: dict[str, Any] = raw_args_obj if isinstance(raw_args_obj, dict) else {}

    scene_id = event.get("scene_id") or raw_args.get("scene_id")
    if not isinstance(scene_id, str) or not scene_id.strip():
        scene_id = f"scene-{tool}"

    return tool, scene_id, raw_args


def _build_prompts(tool: str, scene_id: str, event: dict[str, Any], args: dict[str, Any]) -> tuple[str, str]:
    image_prompt = args.get("image_prompt") or event.get("image_prompt")
    video_prompt = args.get("video_prompt") or event.get("video_prompt")

    prompt = args.get("prompt") or event.get("prompt")

    if isinstance(image_prompt, str) and image_prompt.strip() and isinstance(video_prompt, str) and video_prompt.strip():
        return image_prompt, video_prompt

    if isinstance(prompt, str) and prompt.strip():
        if not isinstance(image_prompt, str) or not image_prompt.strip():
            image_prompt = prompt
        if not isinstance(video_prompt, str) or not video_prompt.strip():
            video_prompt = prompt
        return image_prompt, video_prompt

    visual_traits_obj = args.get("visual_traits")
    visual_traits: list[Any] = visual_traits_obj if isinstance(visual_traits_obj, list) else []
    personality_traits_obj = args.get("personality_traits")
    personality_traits: list[Any] = personality_traits_obj if isinstance(personality_traits_obj, list) else []
    child_context = args.get("child_context") or event.get("child_context") or f"story scene {scene_id}"

    bundle = build_scene_prompts(
        visual_traits=[str(value) for value in visual_traits],
        personality_traits=[str(value) for value in personality_traits],
        child_context=str(child_context),
    )

    if tool == "generate_image":
        return image_prompt or bundle.image_prompt, video_prompt or bundle.video_prompt
    return image_prompt or bundle.image_prompt, video_prompt or bundle.video_prompt


class MediaToolCallInterceptingStream:
    def __init__(self, *, base_stream: Any, media_orchestrator: MediaOrchestratorLike) -> None:
        self._base_stream = base_stream
        self._media_orchestrator: MediaOrchestratorLike = media_orchestrator
        self._queue: asyncio.Queue[dict[str, Any] | bytes] = asyncio.Queue()
        self._pump_task: asyncio.Task[None] | None = None
        self._orchestration_tasks: set[asyncio.Task[None]] = set()
        self._base_done = asyncio.Event()
        self._image_generated = False
        self._video_generated = False
        self._generated_images: dict[str, Any] = {}

    async def send_realtime_audio(self, audio_chunk: bytes) -> None:
        await self._base_stream.send_realtime_audio(audio_chunk)

    async def send_text(self, text: str) -> None:
        await self._base_stream.send_text(text)

    async def _emit_media_event(self, event: dict[str, Any]) -> None:
        self._queue.put_nowait(event)
        await self._notify_model_of_media(event)

    async def _notify_model_of_media(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        scene_id = event.get("scene_id", "unknown")
        if event_type == "media.image.created":
            msg = f"[SYSTEM: Image generated successfully for {scene_id} and is now visible to the child. React warmly in character.]"
        elif event_type == "media.video.created":
            msg = f"[SYSTEM: Video generated successfully for {scene_id} and is now visible to the child. Celebrate this moment warmly in character. Do not start a new story.]"
        else:
            return
        try:
            await self._base_stream.send_text(msg)
        except Exception:
            logger.debug("Failed to send media awareness text for %s", event_type, exc_info=True)

    async def _generate_image_only(self, *, scene_id: str, image_prompt: str) -> None:
        debug_tracer.log_debug(
            event_type="scene_orchestration_started",
            source="interceptor",
            scene_id=scene_id,
        )
        try:
            generated_image = await self._media_orchestrator.generate_image_only(
                scene_id=scene_id,
                image_prompt=image_prompt,
                event_sink=self._emit_media_event,
            )
        except Exception:
            logger.exception("Image generation failed for scene_id=%s", scene_id)
        else:
            if generated_image is not None:
                self._generated_images[scene_id] = generated_image
            debug_tracer.log_debug(
                event_type="scene_orchestration_completed",
                source="interceptor",
                scene_id=scene_id,
            )

    async def _generate_video_only(self, *, scene_id: str, video_prompt: str) -> None:
        debug_tracer.log_debug(
            event_type="scene_orchestration_started",
            source="interceptor",
            scene_id=scene_id,
        )
        try:
            await self._media_orchestrator.generate_video_only(
                scene_id=scene_id,
                video_prompt=video_prompt,
                event_sink=self._emit_media_event,
                imagen_image=self._generated_images.get(scene_id),
            )
        except Exception:
            logger.exception("Video generation failed for scene_id=%s", scene_id)
        else:
            debug_tracer.log_debug(
                event_type="scene_orchestration_completed",
                source="interceptor",
                scene_id=scene_id,
            )

    def _handle_tool_call(self, event: dict[str, Any]) -> None:
        # Classify tool-like events for observability before extraction
        if event.get("type") == "tool_call":
            tool = event.get("tool")
            if not isinstance(tool, str) or tool not in _MEDIA_TOOLS:
                debug_tracer.log_debug(
                    event_type="tool_call_unrecognized",
                    source="interceptor",
                    reason=f"tool={tool!r} not in media tools",
                )

        payload = _extract_tool_call_payload(event)
        if payload is None:
            return

        tool, scene_id, args = payload
        if tool == "generate_image" and self._image_generated:
            debug_tracer.log_debug(
                event_type="tool_call_blocked_session_lock",
                source="interceptor",
                scene_id=scene_id,
                tool=tool,
            )
            return
        if tool == "generate_video" and self._video_generated:
            debug_tracer.log_debug(
                event_type="tool_call_blocked_session_lock",
                source="interceptor",
                scene_id=scene_id,
                tool=tool,
            )
            return

        debug_tracer.log_debug(
            event_type="tool_call_recognized",
            source="interceptor",
            scene_id=scene_id,
            tool=tool,
        )
        image_prompt, video_prompt = _build_prompts(tool=tool, scene_id=scene_id, event=event, args=args)
        if tool == "generate_image":
            self._image_generated = True
            task = asyncio.create_task(
                self._generate_image_only(
                    scene_id=scene_id,
                    image_prompt=image_prompt,
                )
            )
        else:
            self._video_generated = True
            task = asyncio.create_task(
                self._generate_video_only(
                    scene_id=scene_id,
                    video_prompt=video_prompt,
                )
            )
        self._orchestration_tasks.add(task)

        def _cleanup(done_task: asyncio.Task[None]) -> None:
            self._orchestration_tasks.discard(done_task)

        task.add_done_callback(_cleanup)

    async def _pump_base_events(self) -> None:
        try:
            async for event in self._base_stream.iter_events():
                if isinstance(event, dict):
                    self._handle_tool_call(event)
                await self._queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Base stream pump ended with error")
        finally:
            self._base_done.set()

    async def _drain_complete(self) -> bool:
        if not self._base_done.is_set():
            return False
        if self._orchestration_tasks:
            return False
        return self._queue.empty()

    async def _iter(self) -> AsyncIterator[dict[str, Any] | bytes]:
        self._pump_task = asyncio.create_task(self._pump_base_events())
        try:
            while True:
                if await self._drain_complete():
                    break

                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=0.05)
                except TimeoutError:
                    continue

                yield event
        finally:
            if self._pump_task and not self._pump_task.done():
                self._pump_task.cancel()
                await asyncio.gather(self._pump_task, return_exceptions=True)

    def iter_events(self) -> AsyncIterator[dict[str, Any] | bytes]:
        return self._iter()

    async def close(self) -> None:
        for task in list(self._orchestration_tasks):
            task.cancel()
        if self._orchestration_tasks:
            await asyncio.gather(*self._orchestration_tasks, return_exceptions=True)
        await self._base_stream.close()


class MediaToolCallInterceptingClient:
    def __init__(self, *, base_client: Any, media_orchestrator: MediaOrchestratorLike) -> None:
        self._base_client = base_client
        self._media_orchestrator: MediaOrchestratorLike = media_orchestrator

    async def open_stream(self, session_id: str) -> MediaToolCallInterceptingStream:
        base_stream = await self._base_client.open_stream(session_id=session_id)
        return MediaToolCallInterceptingStream(
            base_stream=base_stream,
            media_orchestrator=self._media_orchestrator,
        )


def _build_default_orchestrator() -> MediaOrchestrator | None:
    load_env_once()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        asset_store = build_asset_store()
        return MediaOrchestrator(client=client, asset_store=asset_store)
    except Exception:
        logger.warning("Failed to initialize MediaOrchestrator default client", exc_info=True)
        return None


def maybe_wrap_live_client_with_media_orchestrator(
    *,
    client: Any,
    live_mode: str | None = None,
    media_orchestrator: MediaOrchestratorLike | None = None,
) -> Any:
    load_env_once()
    resolved_mode = (live_mode or os.getenv("ANIMISM_LIVE_MODE", "adk")).lower()
    if resolved_mode in {"mock", "pilot"}:
        debug_tracer.log_debug(
            event_type="interceptor_bypassed",
            source="interceptor",
            mode=resolved_mode,
        )
        return client

    orchestrator = media_orchestrator
    if orchestrator is None:
        orchestrator = _build_default_orchestrator()
    if orchestrator is None:
        debug_tracer.log_debug(
            event_type="interceptor_bypassed",
            source="interceptor",
            mode=resolved_mode,
            reason="orchestrator_unavailable",
        )
        return client

    debug_tracer.log_debug(
        event_type="interceptor_active",
        source="interceptor",
        mode=resolved_mode,
    )
    return MediaToolCallInterceptingClient(
        base_client=client,
        media_orchestrator=orchestrator,
    )
