from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from app.realtime.audio_protocol import AudioFormatError, validate_pcm16_16khz_mono


def _extract_audio_bytes(event: dict[str, Any] | bytes) -> bytes | None:
    if isinstance(event, (bytes, bytearray)):
        return bytes(event)

    if not isinstance(event, dict):
        return None

    if isinstance(event.get("audio"), (bytes, bytearray)):
        return bytes(event["audio"])

    content = event.get("content")
    if not isinstance(content, dict):
        return None

    parts = content.get("parts")
    if not isinstance(parts, list):
        return None

    for part in parts:
        inline_data = part.get("inlineData") if isinstance(part, dict) else None
        if not isinstance(inline_data, dict):
            continue
        mime_type = inline_data.get("mimeType", "")
        raw_data = inline_data.get("data")
        if isinstance(raw_data, str) and mime_type.startswith("audio/"):
            try:
                return base64.b64decode(raw_data)
            except Exception:
                return None
    return None


def _extract_text(event: dict[str, Any] | bytes) -> str | None:
    if not isinstance(event, dict):
        return None
    text = event.get("text")
    if isinstance(text, str):
        return text
    content = event.get("content")
    if not isinstance(content, dict):
        return None
    parts = content.get("parts")
    if not isinstance(parts, list):
        return None
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            return part["text"]
    return None


async def run_duplex_bridge(websocket: Any, gemini_client: Any, session_id: str) -> None:
    stream = await gemini_client.open_stream(session_id=session_id)
    cancel_signal = asyncio.Event()

    def _cancel_other(task: asyncio.Task[Any]) -> None:
        if cancel_signal.is_set():
            return
        cancel_signal.set()
        if task.cancelled():
            return
        if task.exception() is not None:
            return

    async def upstream_task() -> None:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                await stream.send_realtime_audio(message["bytes"])
                continue

            if "text" in message and message["text"] is not None:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError as exc:
                    raise AudioFormatError("Invalid websocket JSON payload") from exc

                if not isinstance(payload, dict):
                    raise AudioFormatError("Unsupported websocket payload")

                message_type = payload.get("type")

                if message_type == "audio_config":
                    validate_pcm16_16khz_mono(
                        {
                            "sample_rate": payload.get("sample_rate"),
                            "channels": payload.get("channels"),
                            "encoding": payload.get("encoding"),
                        }
                    )
                    continue

                if message_type == "text":
                    text = payload.get("text", "")
                    if isinstance(text, str) and text.strip():
                        await stream.send_text(text)
                    continue

                raise AudioFormatError(f"Unsupported websocket message type: {message_type}")

    async def downstream_task() -> None:
        async for event in stream.iter_events():
            if cancel_signal.is_set():
                break

            audio_chunk = _extract_audio_bytes(event)
            if audio_chunk is not None:
                await websocket.send_bytes(audio_chunk)
                continue

            text_content = _extract_text(event)
            if text_content:
                await websocket.send_text(json.dumps({"type": "text", "text": text_content}))

    upstream = asyncio.create_task(upstream_task())
    downstream = asyncio.create_task(downstream_task())
    upstream.add_done_callback(lambda _: _cancel_other(upstream))
    downstream.add_done_callback(lambda _: _cancel_other(downstream))

    async def _await_duplex() -> None:
        await asyncio.gather(upstream, downstream)

    try:
        await _await_duplex()
    except Exception:
        for task in (upstream, downstream):
            if not task.done():
                task.cancel()
        await asyncio.gather(upstream, downstream, return_exceptions=True)
        raise
    finally:
        for task in (upstream, downstream):
            if not task.done():
                task.cancel()
        await asyncio.gather(upstream, downstream, return_exceptions=True)
        await stream.close()
