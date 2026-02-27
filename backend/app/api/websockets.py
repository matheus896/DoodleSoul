import json
import logging

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.realtime.audio_protocol import AudioFormatError
from app.realtime.bridge import run_duplex_bridge
from app.services.live_client_factory import build_live_client


router = APIRouter()
logger = logging.getLogger(__name__)


async def _safe_close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except WebSocketDisconnect:
        logger.debug("WebSocket already disconnected while closing with code=%s", code)


@router.websocket("/ws/live/{session_id}")
async def ws_live(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    client = build_live_client()
    try:
        await run_duplex_bridge(websocket=websocket, gemini_client=client, session_id=session_id)
    except AudioFormatError as error:
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "code": "invalid_audio_format",
                        "message": str(error),
                    }
                )
            )
        except WebSocketDisconnect:
            logger.debug("Client disconnected before invalid audio error payload send")
        await _safe_close(websocket, code=1003)
    except Exception:
        logger.exception("Unhandled error in ws_live session_id=%s", session_id)
        await _safe_close(websocket, code=1011)
