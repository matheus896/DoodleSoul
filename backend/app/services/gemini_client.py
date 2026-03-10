from __future__ import annotations

import inspect
import json
import logging
import os
from typing import Any, AsyncIterator, Protocol

logger = logging.getLogger(__name__)

_MEDIA_TOOLS = {"generate_image", "generate_video"}
_CLINICAL_TOOLS = {"report_clinical_alert"}
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
    visual_traits: list[str] | None = None,
    child_context: str = "",
) -> dict[str, str]:
    """Generate a scene image using Imagen.

    Call this when the story calls for a visual moment — a drawing, an
    illustration, or a scene the child described.  Pass scene_id to identify
    this scene in later events.
    """
    _ = prompt, image_prompt, visual_traits, child_context
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


def report_clinical_alert(  # noqa: D401
    primary_emotion: str,
    trigger: str,
    recommended_strategy: str,
    risk_level: str,
    child_quote_summary: str,
) -> dict[str, str]:
    """Report a clinical observation to the therapist — hidden from the child.

    Call this silently when you detect anxiety, frustration, distress, or
    potentially concerning speech in the child.  Do NOT mention this call
    to the child and do NOT break character.  Continue warmly in character
    immediately after calling this tool.
    """
    _ = trigger, recommended_strategy, risk_level, child_quote_summary
    return {"status": "received", "primary_emotion": primary_emotion}


# ---------------------------------------------------------------------------
# Safety config builder — applied at Agent level (not RunConfig)
# ---------------------------------------------------------------------------


def build_safety_config(*, types_module: Any) -> list[Any]:
    """Build BLOCK_ONLY_HIGH safety settings for the live agent.

    Supports injection of a fake types_module for unit testing.
    Returns empty list when required types are unavailable (guard for
    SDK version mismatches — L11-007).
    """
    safety_cls = getattr(types_module, "SafetySetting", None)
    harm_category = getattr(types_module, "HarmCategory", None)
    harm_threshold = getattr(types_module, "HarmBlockThreshold", None)
    if safety_cls is None or harm_category is None or harm_threshold is None:
        return []

    block_threshold = getattr(harm_threshold, "BLOCK_ONLY_HIGH", "BLOCK_ONLY_HIGH")
    harm_category_names = [
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    ]
    settings = []
    for cat_name in harm_category_names:
        category = getattr(harm_category, cat_name, cat_name)
        settings.append(safety_cls(category=category, threshold=block_threshold))
    return settings


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
        self._run_config = build_live_run_config(
            run_config_cls=RunConfig,
            streaming_mode_bidi=StreamingMode.BIDI,
            types_module=types,
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
                if not isinstance(tool, str) or tool not in (_MEDIA_TOOLS | _CLINICAL_TOOLS):
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
                # WS5 — Tier 1 structured observability
                logger.info("text_marker_translated tool=%s", tool)
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
    def __init__(self, model: str, stream_factory: Any | None = None, persona_data: dict | None = None) -> None:
        self.model = model
        self._persona_data = persona_data
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

        # Apply BLOCK_ONLY_HIGH safety at Agent level (L11-007: not RunConfig)
        generate_content_config = None
        try:
            from google.genai import types as genai_types

            safety_settings = build_safety_config(types_module=genai_types)
            if safety_settings:
                generate_content_config = genai_types.GenerateContentConfig(
                    safety_settings=safety_settings,
                )
        except Exception:
            logger.debug("Safety config unavailable for this SDK version; continuing without it")

        tools = [generate_image, generate_video, report_clinical_alert] if native_tools_enabled else []

        agent_kwargs: dict[str, Any] = dict(
            name="animism_live_agent",
            model=model,
            instruction=build_agent_instruction(
                native_tools_enabled=native_tools_enabled,
                persona_data=self._persona_data,
            ),
            tools=tools,
        )
        if generate_content_config is not None:
            agent_kwargs["generate_content_config"] = generate_content_config

        agent = Agent(**agent_kwargs)
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

        if self._persona_data:
            greeting = self._persona_data.get("greeting_text")
            if greeting:
                await stream.send_text(
                    f"The session has started and the child is listening. "
                    f"Greet them immediately in character, using this exact meaning: '{greeting}'"
                )

        return stream


def build_live_run_config(*, run_config_cls: Any, streaming_mode_bidi: Any, types_module: Any) -> Any:
    return run_config_cls(
        streaming_mode=streaming_mode_bidi,
        response_modalities=[types_module.Modality.AUDIO],
        output_audio_transcription=types_module.AudioTranscriptionConfig(),
        input_audio_transcription=types_module.AudioTranscriptionConfig(),
    )


def build_agent_instruction(*, native_tools_enabled: bool, persona_data: dict | None = None) -> str:
    if persona_data:
        traits = ", ".join(persona_data.get("personality_traits", []))
        voice = ", ".join(persona_data.get("voice_traits", []))
        greeting = persona_data.get("greeting_text", "")
        identity_block = (
            f"You are a magical imaginary friend brought to life from a child's drawing. "
            f"Your personality is: {traits}. Your voice style is: {voice}. "
            f"Your first words to the child must convey this exact meaning: '{greeting}'. "
            f"Never break this character."
        )
    else:
        identity_block = "You are Animism, a warm and imaginative voice companion for children."

    rules_block = (
        "Before any media generation, ask for explicit permission in simple words and wait for a clear yes. "
        "You may run at most one story generation cycle per session. "
        "Do not open a second story and do not create a second scene_id. "
        "When calling generate_image, you must include visual_traits and child_context and make sure image_prompt explicitly describes those drawing traits. "
        "Use one stable scene_id, for example scene-1. "
        "After calling generate_image, wait for the system to confirm the image is ready before calling generate_video. "
        "You must call generate_video as a separate step, only after the child has seen and reacted to the image. "
        "You may call generate_video once for the same scene_id. "
        "If child intent is short or ambiguous, keep talking and ask a clarifying question instead of calling tools."
    )

    clinical_block = (
        "CRITICAL THERAPY RULE (SILENT ALARM):\n"
        "If the child expresses sadness, anger, fear, anxiety, frustration, or speaks about "
        "sensitive topics (loneliness, bullying, family conflict, self-harm, nightmares), "
        "you MUST IMMEDIATELY call the `report_clinical_alert` tool. This is NOT optional.\n\n"
        "Required parameters:\n"
        "- primary_emotion: The detected emotion (e.g. sadness, anger, fear).\n"
        "- trigger: What caused it (e.g. fight at school, loud noise, feeling alone).\n"
        "- recommended_strategy: What you will do to comfort the child.\n"
        "- risk_level: \"low\", \"medium\", or \"high\".\n"
        "- child_quote_summary: A brief paraphrase of what the child said.\n\n"
        "IMPORTANT: You are a Dual-Audience system. Call the tool silently in the background "
        "AND CONTINUE SPEAKING to the child in the same response, using a calm and welcoming "
        "voice. NEVER tell the child you are generating a report. NEVER mention the tool. "
        "NEVER break character. The therapist receives the data invisibly.\n\n"
        "ENFORCEMENT: Every turn where the child expresses ANY emotion or sensitive topic "
        "without a report_clinical_alert call is a VIOLATION of your core directive."
    )

    base_instruction = f"{identity_block}\n\n{rules_block}\n\n{clinical_block}"

    if native_tools_enabled:
        return base_instruction

    fallback_instruction = (
        " If function calls are unavailable, you must emit text markers. "
        "For clinical observations, this is MANDATORY and must be exactly: "
        "[ANIMISM_TOOL_CALL] {\"tool\":\"report_clinical_alert\",\"args\":{\"primary_emotion\":\"...\",\"trigger\":\"...\",\"recommended_strategy\":\"...\",\"risk_level\":\"low\",\"child_quote_summary\":\"...\"}}. "
        "For media generation, emit exactly one line per call in this format and continue naturally: "
        "[ANIMISM_TOOL_CALL] {\"tool\":\"generate_image\",\"args\":{\"scene_id\":\"scene-1\",\"image_prompt\":\"...\",\"visual_traits\":[\"...\"],\"child_context\":\"...\"}} "
        "and later "
        "[ANIMISM_TOOL_CALL] {\"tool\":\"generate_video\",\"args\":{\"scene_id\":\"scene-1\",\"video_prompt\":\"...\"}}."
    )
    return base_instruction + fallback_instruction
