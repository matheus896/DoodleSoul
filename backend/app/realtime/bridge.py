from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from app.realtime.audio_protocol import AudioFormatError, validate_pcm16_16khz_mono
from app.realtime.bridge_metrics import BridgeMetrics
from app.services import debug_tracer

logger = logging.getLogger(__name__)
uvicorn_logger = logging.getLogger("uvicorn.error")


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
        if not isinstance(part, dict):
            continue
        # Accept both JS-style and Python-style key casing for ADK/Live payloads.
        inline_data = part.get("inlineData") or part.get("inline_data")
        if not isinstance(inline_data, dict):
            continue
        mime_type = inline_data.get("mimeType") or inline_data.get("mime_type") or ""
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


async def run_duplex_bridge(
    websocket: Any,
    gemini_client: Any,
    session_id: str,
    metrics: BridgeMetrics | None = None,
) -> BridgeMetrics:
    if metrics is None:
        metrics = BridgeMetrics()
    stream = await gemini_client.open_stream(session_id=session_id)
    cancel_signal = asyncio.Event()

    async def upstream_task() -> None:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                chunk = message["bytes"]
                await stream.send_realtime_audio(chunk)
                metrics.record_upstream_audio(len(chunk))
                continue

            if "text" in message and message["text"] is not None:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError as exc:
                    metrics.record_error()
                    raise AudioFormatError("Invalid websocket JSON payload") from exc

                if not isinstance(payload, dict):
                    metrics.record_error()
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
                        metrics.record_upstream_text()
                    continue

                metrics.record_error()
                raise AudioFormatError(f"Unsupported websocket message type: {message_type}")

    async def downstream_task() -> None:
        async for event in stream.iter_events():
            if cancel_signal.is_set():
                break

            if isinstance(event, dict) and isinstance(event.get("audio"), (bytes, bytearray)):
                audio_chunk = bytes(event["audio"])
                await websocket.send_bytes(audio_chunk)
                metrics.record_downstream_audio(len(audio_chunk))
                continue

            if isinstance(event, dict):
                await websocket.send_text(json.dumps(event))
                audio_chunk = _extract_audio_bytes(event)
                if audio_chunk is not None:
                    metrics.record_downstream_audio(len(audio_chunk))
                text_content = _extract_text(event)
                if text_content:
                    metrics.record_downstream_text()
                debug_tracer.log_debug(
                    event_type="downstream_event",
                    source="bridge",
                    session_id=session_id,
                    scene_id=event.get("scene_id") if isinstance(event.get("scene_id"), str) else None,
                    event_kind=event.get("type"),
                )
                continue

            audio_chunk = _extract_audio_bytes(event)
            if audio_chunk is not None:
                await websocket.send_bytes(audio_chunk)
                metrics.record_downstream_audio(len(audio_chunk))
                continue

            text_content = _extract_text(event)
            if text_content:
                await websocket.send_text(json.dumps({"type": "text", "text": text_content}))
                metrics.record_downstream_text()

    upstream = asyncio.create_task(upstream_task())
    downstream = asyncio.create_task(downstream_task())

    async def _await_duplex() -> None:
        done, pending = await asyncio.wait(
            {upstream, downstream},
            return_when=asyncio.FIRST_COMPLETED,
        )

        cancel_signal.set()
        for task in pending:
            task.cancel()

        await asyncio.gather(*pending, return_exceptions=True)

        for task in done:
            if task.cancelled():
                continue
            exception = task.exception()
            if exception is not None:
                raise exception

    try:
        await _await_duplex()
    except Exception:
        metrics.record_error()
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
        snapshot = metrics.snapshot()
        logger.info("bridge_metrics session=%s %s", session_id, snapshot)

    return metrics
