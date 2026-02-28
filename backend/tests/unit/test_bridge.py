from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.realtime.bridge import run_duplex_bridge
from app.realtime.audio_protocol import AudioFormatError
from app.main import app


class FakeWebSocket:
    def __init__(self, messages: list[dict] | None = None) -> None:
        self._messages = messages or []
        self.sent_bytes: list[bytes] = []
        self.sent_text: list[str] = []

    async def receive(self):
        if self._messages:
            return self._messages.pop(0)
        return {"type": "websocket.disconnect"}

    async def send_bytes(self, payload: bytes) -> None:
        self.sent_bytes.append(payload)

    async def send_text(self, payload: str) -> None:
        self.sent_text.append(payload)


class FakeStream:
    def __init__(self, events: list[dict | bytes] | None = None) -> None:
        self.upstream_audio: list[bytes] = []
        self.upstream_text: list[str] = []
        self._events_data = events or []
        self.closed = False

    async def send_realtime_audio(self, audio_chunk: bytes) -> None:
        self.upstream_audio.append(audio_chunk)

    async def send_text(self, text: str) -> None:
        self.upstream_text.append(text)

    async def close(self) -> None:
        self.closed = True

    async def _events(self):
        for event in self._events_data:
            yield event
            await asyncio.sleep(0)

    def iter_events(self):
        return self._events()


class FakeGeminiClient:
    def __init__(self, stream: FakeStream | None = None) -> None:
        self.stream = stream or FakeStream()

    async def open_stream(self, session_id: str):
        assert session_id == "s1"
        return self.stream


class BlockingStream(FakeStream):
    async def _events(self):
        while True:
            await asyncio.sleep(3600)
            yield {}


class DisconnectingWebSocket(FakeWebSocket):
    async def receive(self):
        raise RuntimeError("receive failed")


@pytest.mark.asyncio
async def test_run_duplex_bridge_forwards_audio_both_directions() -> None:
    websocket = FakeWebSocket(
        messages=[{"bytes": b"input-audio"}, {"type": "websocket.disconnect"}]
    )
    gemini_client = FakeGeminiClient(stream=FakeStream(events=[{"audio": b"output-audio"}]))

    await run_duplex_bridge(websocket=websocket, gemini_client=gemini_client, session_id="s1")

    assert gemini_client.stream.upstream_audio == [b"input-audio"]
    assert websocket.sent_bytes == [b"output-audio"]
    assert gemini_client.stream.closed is True


@pytest.mark.asyncio
async def test_run_duplex_bridge_forwards_text_messages() -> None:
    websocket = FakeWebSocket(
        messages=[
            {"text": json.dumps({"type": "text", "text": "hello"})},
            {"type": "websocket.disconnect"},
        ]
    )
    gemini_client = FakeGeminiClient(stream=FakeStream())

    await run_duplex_bridge(websocket=websocket, gemini_client=gemini_client, session_id="s1")

    assert gemini_client.stream.upstream_text == ["hello"]


@pytest.mark.asyncio
async def test_run_duplex_bridge_rejects_invalid_audio_config() -> None:
    websocket = FakeWebSocket(
        messages=[
            {
                "text": json.dumps(
                    {
                        "type": "audio_config",
                        "sample_rate": 48000,
                        "channels": 1,
                        "encoding": "pcm_s16le",
                    }
                )
            }
        ]
    )
    gemini_client = FakeGeminiClient(stream=FakeStream())

    with pytest.raises(AudioFormatError):
        await run_duplex_bridge(websocket=websocket, gemini_client=gemini_client, session_id="s1")


@pytest.mark.asyncio
async def test_run_duplex_bridge_cancels_sibling_and_closes_stream_on_failure() -> None:
    websocket = DisconnectingWebSocket()
    stream = FakeStream(events=[{"audio": b"output-audio"}])
    gemini_client = FakeGeminiClient(stream=stream)

    with pytest.raises(RuntimeError):
        await run_duplex_bridge(websocket=websocket, gemini_client=gemini_client, session_id="s1")

    assert stream.closed is True


@pytest.mark.asyncio
async def test_run_duplex_bridge_emits_metrics_to_uvicorn_logger(caplog) -> None:
    websocket = FakeWebSocket(
        messages=[{"bytes": b"input-audio"}, {"type": "websocket.disconnect"}]
    )
    gemini_client = FakeGeminiClient(stream=FakeStream(events=[{"audio": b"output-audio"}]))

    with caplog.at_level("INFO", logger="uvicorn.error"):
        await run_duplex_bridge(websocket=websocket, gemini_client=gemini_client, session_id="s1")

    assert any(
        record.name == "uvicorn.error" and "bridge_metrics session=s1" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_run_duplex_bridge_cancels_blocked_downstream_on_disconnect() -> None:
    websocket = FakeWebSocket(messages=[{"type": "websocket.disconnect"}])
    stream = BlockingStream()
    gemini_client = FakeGeminiClient(stream=stream)

    await asyncio.wait_for(
        run_duplex_bridge(websocket=websocket, gemini_client=gemini_client, session_id="s1"),
        timeout=0.5,
    )

    assert stream.closed is True


def test_websocket_route_fail_fast_invalid_config(monkeypatch) -> None:
    monkeypatch.setenv("ANIMISM_LIVE_MODE", "mock")
    client = TestClient(app)

    with client.websocket_connect("/ws/live/s1") as ws:
        ws.send_text(
            json.dumps(
                {
                    "type": "audio_config",
                    "sample_rate": 48000,
                    "channels": 1,
                    "encoding": "pcm_s16le",
                }
            )
        )
        payload = json.loads(ws.receive_text())
        assert payload["type"] == "error"
        assert payload["code"] == "invalid_audio_format"
