"""Tests for Session End with Sign-off and Safe Cleanup (Story 5.2)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.session import _session_grounding_store, _consent_store


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_post_session_end_success(client: TestClient) -> None:
    # Arrange: Setup an active session
    res_start = client.post("/api/session/start", json={"caregiver_consent": True})
    session_id = res_start.json()["data"]["session_id"]
    
    assert _session_grounding_store.has_session(session_id)
    assert _session_grounding_store.is_closed(session_id) is False

    # Act: End the session
    res_end = client.post(f"/api/session/{session_id}/end")

    # Assert: Should be closed and idempotent
    assert res_end.status_code == 200
    assert res_end.json()["status"] == "ok"
    assert res_end.json()["data"]["session_id"] == session_id
    assert "ended_at" in res_end.json()["data"]

    # Verify state in store
    assert _session_grounding_store.is_closed(session_id) is True

    # Calling it again should be idempotent 
    res_end_again = client.post(f"/api/session/{session_id}/end")
    assert res_end_again.status_code == 200


def test_post_session_end_not_found(client: TestClient) -> None:
    res = client.post("/api/session/invalid-id/end")
    assert res.status_code == 404
    assert res.json()["status"] == "error"
    assert res.json()["error"]["code"] == "session_not_found"


from starlette.websockets import WebSocketDisconnect

@pytest.mark.asyncio
async def test_ws_live_rejects_closed_session(client: TestClient) -> None:
    # End a session
    res_start = client.post("/api/session/start", json={"caregiver_consent": True})
    session_id = res_start.json()["data"]["session_id"]
    client.post(f"/api/session/{session_id}/end")

    # Trying to connect a websocket to a closed session should fail
    # Starlette testclient might return a close message or raise WebSocketDisconnect
    try:
        with client.websocket_connect(f"/ws/live/{session_id}") as ws:
            msg = ws.receive()
            if isinstance(msg, dict):
                assert msg.get("type") == "websocket.close"
                assert msg.get("code") == 1008
    except WebSocketDisconnect as exc:
        assert exc.code == 1008
