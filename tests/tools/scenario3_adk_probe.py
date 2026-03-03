from __future__ import annotations

import argparse
import asyncio
import json
import math
import struct
import time
import uuid
from pathlib import Path
from typing import Any

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'websockets'. Install in backend venv: pip install websockets"
    ) from exc


def _pcm16_tone_chunk(*, sample_rate: int = 16000, duration_ms: int = 20, freq_hz: int = 220, amplitude: int = 1800) -> bytes:
    samples = sample_rate * duration_ms // 1000
    data = bytearray(samples * 2)
    for i in range(samples):
        value = int(amplitude * math.sin(2.0 * math.pi * freq_hz * (i / sample_rate)))
        struct.pack_into("<h", data, i * 2, max(-32768, min(32767, value)))
    return bytes(data)


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


async def run_probe(*, ws_url: str, runtime_s: int, output_json: Path) -> None:
    session_id = f"scenario3-adk-{uuid.uuid4().hex[:8]}"
    uri = ws_url.format(session_id=session_id)

    events: list[dict[str, Any]] = []
    audio_downstream_chunks = 0
    close_error: str | None = None

    stop = asyncio.Event()

    async with websockets.connect(uri, max_size=5_000_000) as ws:
        await ws.send(json.dumps({
            "type": "audio_config",
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "pcm_s16le",
        }))

        prompt = (
            "Please call generate_image with scene_id 'scene-real-1' and a child-safe image_prompt, "
            "then call generate_video with the same scene_id and a matching video_prompt. "
            "Announce each step naturally."
        )
        await ws.send(json.dumps({"type": "text", "text": prompt}))

        async def sender() -> None:
            nonlocal close_error
            chunk = _pcm16_tone_chunk()
            deadline = time.monotonic() + runtime_s
            while time.monotonic() < deadline:
                try:
                    await ws.send(chunk)
                except ConnectionClosed as exc:
                    close_error = f"code={exc.code} reason={exc.reason}"
                    stop.set()
                    break
                await asyncio.sleep(0.02)
            stop.set()

        async def receiver() -> None:
            nonlocal audio_downstream_chunks, close_error
            while not stop.is_set():
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except ConnectionClosed as exc:
                    close_error = f"code={exc.code} reason={exc.reason}"
                    stop.set()
                    break

                if isinstance(message, bytes):
                    audio_downstream_chunks += 1
                    continue

                if isinstance(message, (bytearray, memoryview)):
                    audio_downstream_chunks += 1
                    continue

                payload = _safe_json_loads(message)
                if payload is None:
                    events.append({"type": "non_json_text", "raw": message})
                else:
                    events.append(payload)

        await asyncio.gather(sender(), receiver(), return_exceptions=True)

    output_json.parent.mkdir(parents=True, exist_ok=True)

    media_events = [
        e for e in events
        if isinstance(e, dict)
        and isinstance(e.get("type"), str)
        and (
            e.get("type") == "drawing_in_progress"
            or str(e.get("type")).startswith("media.")
            or e.get("type") == "media_delayed"
            or e.get("type") == "tool_call"
        )
    ]

    output = {
        "session_id": session_id,
        "ws_url": uri,
        "runtime_s": runtime_s,
        "captured_at_ms": int(time.time() * 1000),
        "close_error": close_error,
        "audio_downstream_chunks": audio_downstream_chunks,
        "event_count": len(events),
        "media_related_event_count": len(media_events),
        "media_related_events": media_events,
        "all_events": events,
    }
    output_json.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"[scenario3_adk_probe] session_id={session_id}")
    print(f"[scenario3_adk_probe] events={len(events)} media_events={len(media_events)}")
    print(f"[scenario3_adk_probe] output={output_json}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ADK WebSocket probe for Epic 3 Scenario 3 evidence")
    parser.add_argument(
        "--ws-url",
        default="ws://127.0.0.1:8000/ws/live/{session_id}",
        help="WebSocket URL template; must include {session_id}",
    )
    parser.add_argument("--runtime-s", type=int, default=65)
    parser.add_argument(
        "--output",
        default="A:/hackaton-google/tests/output/scenario3_adk_probe_events.json",
    )
    args = parser.parse_args()

    asyncio.run(
        run_probe(
            ws_url=args.ws_url,
            runtime_s=args.runtime_s,
            output_json=Path(args.output),
        )
    )


if __name__ == "__main__":
    main()
