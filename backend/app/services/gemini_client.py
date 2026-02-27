from __future__ import annotations

import inspect
import os
from typing import Any, AsyncIterator, Protocol


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

    async def _iter_runner_events(self) -> AsyncIterator[dict[str, Any] | bytes]:
        await self._ensure_initialized()
        async for event in self._runner.run_live(
            user_id=self._user_id,
            session_id=self._session_id,
            live_request_queue=self._queue,
            run_config=self._run_config,
        ):
            if hasattr(event, "model_dump"):
                yield event.model_dump(mode="json")
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

        agent = Agent(
            name="animism_live_agent",
            model=model,
            instruction="You are a helpful conversational voice companion for children.",
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
