from __future__ import annotations

import pytest

from app.api import websockets


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.closed_codes: list[int] = []
        self.sent_text: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int) -> None:
        self.closed_codes.append(code)

    async def send_text(self, payload: str) -> None:
        self.sent_text.append(payload)


@pytest.mark.asyncio
async def test_ws_live_retries_once_on_early_provider_1008(monkeypatch) -> None:
    ws = FakeWebSocket()
    attempts = {"count": 0}
    sleep_calls: list[float] = []

    def _build_client() -> object:
        return object()

    def _wrap_client(*, client: object):
        return client

    async def _bridge(*, websocket, gemini_client, session_id: str) -> None:
        _ = websocket, gemini_client, session_id
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("APIError: 1008 None. Operation is not implemented")

    async def _sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monotonic_values = [100.0, 101.0]

    def _monotonic() -> float:
        if monotonic_values:
            return monotonic_values.pop(0)
        return 101.0

    monkeypatch.setattr(websockets, "build_live_client", _build_client)
    monkeypatch.setattr(websockets, "maybe_wrap_live_client_with_media_orchestrator", _wrap_client)
    monkeypatch.setattr(websockets, "run_duplex_bridge", _bridge)
    monkeypatch.setattr(websockets.asyncio, "sleep", _sleep)
    monkeypatch.setattr(websockets.time, "monotonic", _monotonic)

    await websockets.ws_live(ws, "s1")

    assert ws.accepted is True
    assert attempts["count"] == 2
    assert sleep_calls == [1.0]
    assert ws.closed_codes == []


@pytest.mark.asyncio
async def test_ws_live_does_not_retry_1008_outside_startup_window(monkeypatch) -> None:
    ws = FakeWebSocket()
    attempts = {"count": 0}

    def _build_client() -> object:
        return object()

    def _wrap_client(*, client: object):
        return client

    async def _bridge(*, websocket, gemini_client, session_id: str) -> None:
        _ = websocket, gemini_client, session_id
        attempts["count"] += 1
        raise RuntimeError("APIError: 1008 None. Operation is not implemented")

    async def _sleep(delay: float) -> None:
        _ = delay

    monotonic_values = [50.0, 60.0]

    def _monotonic() -> float:
        if monotonic_values:
            return monotonic_values.pop(0)
        return 60.0

    monkeypatch.setattr(websockets, "build_live_client", _build_client)
    monkeypatch.setattr(websockets, "maybe_wrap_live_client_with_media_orchestrator", _wrap_client)
    monkeypatch.setattr(websockets, "run_duplex_bridge", _bridge)
    monkeypatch.setattr(websockets.asyncio, "sleep", _sleep)
    monkeypatch.setattr(websockets.time, "monotonic", _monotonic)

    await websockets.ws_live(ws, "s1")

    assert ws.accepted is True
    assert attempts["count"] == 1
    assert ws.closed_codes == [1011]
