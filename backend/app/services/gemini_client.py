from __future__ import annotations

import inspect
import json
import logging
import os
from typing import Any, AsyncIterator, Protocol

logger = logging.getLogger(__name__)

_MEDIA_TOOLS = {"generate_image", "generate_video"}
_TEXT_TOOL_MARKER = "[ANIMISM_TOOL_CALL]"


# ---------------------------------------------------------------------------
# ADK tool stubs — declared on the Agent so Gemini can call them.
# These stubs return immediately; real orchestration is handled by
# MediaToolCallInterceptingStream via the tool_call event translation below.
# ---------------------------------------------------------------------------

def generate_image(  # noqa: D401
    scene_id: str,
    prompt: str = "",
    image_prompt: str = "",
) -> dict[str, str]:
    """Generate a scene image using Imagen.

    Call this when the story calls for a visual moment — a drawing, an
    illustration, or a scene the child described.  Pass scene_id to identify
    this scene in later events.
    """
    return {"status": "acknowledged", "scene_id": scene_id}


def generate_video(  # noqa: D401
    scene_id: str,
    prompt: str = "",
    video_prompt: str = "",
) -> dict[str, str]:
    """Generate a short animated scene using Veo.

    Call this when you want to bring a scene to life with motion.  Use the
    same scene_id as the preceding generate_image call when applicable.
    """
    return {"status": "acknowledged", "scene_id": scene_id}


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class GeminiLiveStream(Protocol):
    async def send_realtime_audio(self, audio_chunk: bytes) -> None: ...

    async def send_text(self, text: str) -> None: ...

    def iter_events(self) -> AsyncIterator[dict[str, Any] | bytes]: ...

    async def close(self) -> None: ...


class AdkGeminiLiveStream:
    def __init__(self, *, runner: Any, session_service: Any, model: str, session_id: str) -> None:
        self._runner = runner
        self._session_service = session_service
        self._model = model
        self._session_id = session_id
        self._user_id = "live-user"
        self._app_name = "animism-studio"
        self._queue = None
        self._run_config = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        from google.adk.agents.live_request_queue import LiveRequestQueue
        from google.adk.agents.run_config import RunConfig, StreamingMode
        from google.genai import types

        self._queue = LiveRequestQueue()
        self._run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            response_modalities=[types.Modality.AUDIO],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
        )
        await self._session_service.create_session(
            app_name=self._app_name,
            user_id=self._user_id,
            session_id=self._session_id,
        )
        self._initialized = True

    async def _maybe_await(self, result: Any) -> None:
        if inspect.isawaitable(result):
            await result

    async def send_realtime_audio(self, audio_chunk: bytes) -> None:
        await self._ensure_initialized()

        from google.genai import types

        blob = types.Blob(mime_type="audio/pcm;rate=16000", data=audio_chunk)
        await self._maybe_await(self._queue.send_realtime(blob))

    async def send_text(self, text: str) -> None:
        await self._ensure_initialized()

        from google.genai import types

        content = types.Content(role="user", parts=[types.Part(text=text)])
        await self._maybe_await(self._queue.send_content(content))

    @staticmethod
    def _translate_function_calls(dumped: dict[str, Any]) -> list[dict[str, Any]]:
        """Translate ADK requested_function_calls to interceptor tool_call format.

        ADK emits function calls in ``event.actions.requested_function_calls``.
        The MediaToolCallInterceptingStream expects ``{type: "tool_call", tool, args}``.
        This translation is emitted BEFORE the original ADK event so the interceptor
        can fire orchestration while the ADK event continues downstream.
        """
        actions: dict[str, Any] = dumped.get("actions") or {}
        raw_calls: list[Any] = actions.get("requested_function_calls") or []
        translated: list[dict[str, Any]] = []

        def _normalize_args(raw_args: Any, fallback: Any) -> dict[str, Any]:
            if isinstance(raw_args, dict):
                return raw_args
            if isinstance(raw_args, str):
                try:
                    parsed = json.loads(raw_args)
                except json.JSONDecodeError:
                    return {}
                if isinstance(parsed, dict):
                    return parsed
                return {}
            if isinstance(fallback, dict):
                return fallback
            return {}

        for fc in raw_calls:
            if not isinstance(fc, dict):
                continue
            name: str = fc.get("name") or ""
            if not name:
                continue
            args: dict[str, Any] = _normalize_args(fc.get("args"), fc.get("arguments"))
            translated.append({
                "type": "tool_call",
                "tool": name,
                "args": args,
                # scene_id promoted to top level for interceptor convenience
                "scene_id": args.get("scene_id") or "",
            })

        if translated:
            return translated

        return AdkGeminiLiveStream._translate_text_tool_markers(dumped)

    @staticmethod
    def _translate_text_tool_markers(dumped: dict[str, Any]) -> list[dict[str, Any]]:
        """Translate explicit text markers into tool_call events.

        Marker format (single line):
            [ANIMISM_TOOL_CALL] {"tool":"generate_image","args":{"scene_id":"scene-1"}}

        This is a fallback path for runtimes where native live tool-calling
        may be unavailable for the selected model/project.
        """
        content: dict[str, Any] = dumped.get("content") or {}
        parts: list[Any] = content.get("parts") or []
        translated: list[dict[str, Any]] = []
        candidate_texts: list[str] = []

        output_transcription = dumped.get("output_transcription")
        if isinstance(output_transcription, dict):
            maybe_text = output_transcription.get("text")
            if isinstance(maybe_text, str) and maybe_text:
                candidate_texts.append(maybe_text)

        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text:
                candidate_texts.append(text)

        for text in candidate_texts:
            if _TEXT_TOOL_MARKER not in text:
                continue
            scan_pos = 0
            while True:
                marker_pos = text.find(_TEXT_TOOL_MARKER, scan_pos)
                if marker_pos < 0:
                    break

                raw_candidate = text[marker_pos + len(_TEXT_TOOL_MARKER):].lstrip()
                if not raw_candidate:
                    break

                try:
                    marker_payload, consumed = json.JSONDecoder().raw_decode(raw_candidate)
                except json.JSONDecodeError:
                    scan_pos = marker_pos + len(_TEXT_TOOL_MARKER)
                    continue
                if not isinstance(marker_payload, dict):
                    scan_pos = marker_pos + len(_TEXT_TOOL_MARKER) + consumed
                    continue

                tool = marker_payload.get("tool")
                args = marker_payload.get("args")
                if not isinstance(tool, str) or tool not in _MEDIA_TOOLS:
                    scan_pos = marker_pos + len(_TEXT_TOOL_MARKER) + consumed
                    continue
                if not isinstance(args, dict):
                    args = {}

                translated.append({
                    "type": "tool_call",
                    "tool": tool,
                    "args": args,
                    "scene_id": args.get("scene_id") or "",
                })
                scan_pos = marker_pos + len(_TEXT_TOOL_MARKER) + consumed

        return translated

    async def _iter_runner_events(self) -> AsyncIterator[dict[str, Any] | bytes]:
        await self._ensure_initialized()
        async for event in self._runner.run_live(
            user_id=self._user_id,
            session_id=self._session_id,
            live_request_queue=self._queue,
            run_config=self._run_config,
        ):
            if hasattr(event, "model_dump"):
                dumped: dict[str, Any] = event.model_dump(mode="json")
                # Emit translated tool_call events BEFORE the original ADK event
                for tool_call_event in self._translate_function_calls(dumped):
                    logger.debug(
                        "ADK function call translated: tool=%s scene_id=%s",
                        tool_call_event.get("tool"),
                        tool_call_event.get("scene_id"),
                    )
                    yield tool_call_event
                yield dumped
                continue
            yield event

    def iter_events(self) -> AsyncIterator[dict[str, Any] | bytes]:
        return self._iter_runner_events()

    async def close(self) -> None:
        if self._queue is not None:
            self._queue.close()


class GeminiLiveClient:
    def __init__(self, model: str, stream_factory: Any | None = None) -> None:
        self.model = model
        self._stream_factory = stream_factory or self._build_adk_stream

    async def _build_adk_stream(self, *, model: str, session_id: str) -> GeminiLiveStream:
        from google.adk.agents import Agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for Gemini Live API")

        tool_mode = os.getenv("ANIMISM_ADK_TOOL_MODE", "native").lower()
        native_tools_enabled = tool_mode != "text_fallback"

        base_instruction = (
            "You are Animism, a warm and imaginative voice companion for children. "
            "When the child's story or conversation calls for a visual moment — "
            "something to draw, paint, or bring to life — call generate_image with "
            "a scene_id (e.g. 'scene-1') and a vivid image_prompt describing what "
            "to generate.  After an image is shown, you may call generate_video with "
            "the same scene_id to animate it.  Keep the scene_id unique per creative "
            "moment in the session."
        )

        fallback_instruction = (
            " If function calls are unavailable, emit exactly one line per call in this "
            "format and continue naturally: "
            "[ANIMISM_TOOL_CALL] {\"tool\":\"generate_image\",\"args\":{\"scene_id\":\"scene-1\",\"image_prompt\":\"...\"}} "
            "and later "
            "[ANIMISM_TOOL_CALL] {\"tool\":\"generate_video\",\"args\":{\"scene_id\":\"scene-1\",\"video_prompt\":\"...\"}}."
        )

        agent = Agent(
            name="animism_live_agent",
            model=model,
            instruction=base_instruction + (fallback_instruction if not native_tools_enabled else ""),
            tools=[generate_image, generate_video] if native_tools_enabled else [],
        )
        session_service = InMemorySessionService()
        runner = Runner(
            app_name="animism-studio",
            agent=agent,
            session_service=session_service,
        )
        return AdkGeminiLiveStream(
            runner=runner,
            session_service=session_service,
            model=model,
            session_id=session_id,
        )

    async def open_stream(self, session_id: str) -> GeminiLiveStream:
        stream = self._stream_factory(model=self.model, session_id=session_id)
        if hasattr(stream, "__await__"):
            stream = await stream
        return stream
