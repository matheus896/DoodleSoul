import json
import logging
import time

import asyncio

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.realtime.audio_protocol import AudioFormatError
from app.realtime.bridge import run_duplex_bridge
from app.realtime.bridge_metrics import BridgeMetrics
from app.services import debug_tracer
from app.services.live_client_factory import build_live_client
from app.services.live_media_interceptor import maybe_wrap_live_client_with_media_orchestrator


router = APIRouter()
logger = logging.getLogger(__name__)

_RETRYABLE_STARTUP_WINDOW_S = 5.0
_STARTUP_RETRY_BACKOFF_S = 1.0
_MAX_BRIDGE_ATTEMPTS = 2


async def _safe_close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except WebSocketDisconnect:
        logger.debug("WebSocket already disconnected while closing with code=%s", code)


def _is_provider_live_path_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(token in message for token in ("apierror", "1008", "1011", "opening handshake", "startstep"))


def _is_retryable_provider_startup_error(error: Exception, *, elapsed_s: float, attempt: int) -> bool:
    if attempt >= (_MAX_BRIDGE_ATTEMPTS - 1):
        return False
    if elapsed_s > _RETRYABLE_STARTUP_WINDOW_S:
        return False

    message = str(error).lower()
    retryable_tokens = (
        "1008",
        "operation is not implemented",
        "timed out during opening handshake",
        "opening handshake",
    )
    return any(token in message for token in retryable_tokens)


def _extract_provider_error_code(error: Exception) -> str | None:
    message = str(error).lower()
    for code in ("1008", "1011"):
        if code in message:
            return code
    return None


def _build_provider_failure_context(
    error: Exception,
    *,
    elapsed_s: float,
    attempt: int,
    bridge_metrics: BridgeMetrics,
    will_retry: bool,
) -> dict[str, object]:
    if elapsed_s > _RETRYABLE_STARTUP_WINDOW_S:
        classification = "provider_runtime_failure"
        retry_context = "outside_startup_window"
    elif will_retry:
        classification = "provider_startup_failure"
        retry_context = "startup_retry"
    else:
        classification = "provider_startup_failure"
        retry_context = "startup_retry_exhausted"

    return {
        "classification": classification,
        "error_origin": "provider_live_path",
        "provider_error_code": _extract_provider_error_code(error),
        "attempt": attempt + 1,
        "max_attempts": _MAX_BRIDGE_ATTEMPTS,
        "elapsed_s": round(elapsed_s, 3),
        "retry_context": retry_context,
        "bridge_health": bridge_metrics.snapshot(),
    }


@router.websocket("/ws/live/{session_id}")
async def ws_live(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session_start = time.monotonic()

    for attempt in range(_MAX_BRIDGE_ATTEMPTS):
        base_client = build_live_client()
        client = maybe_wrap_live_client_with_media_orchestrator(client=base_client)
        bridge_metrics = BridgeMetrics()
        try:
            await run_duplex_bridge(
                websocket=websocket,
                gemini_client=client,
                session_id=session_id,
                metrics=bridge_metrics,
            )
            return
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
            return
        except Exception as error:
            elapsed_s = time.monotonic() - session_start
            retryable_startup_error = _is_retryable_provider_startup_error(
                error,
                elapsed_s=elapsed_s,
                attempt=attempt,
            )

            if _is_provider_live_path_error(error):
                failure_context = _build_provider_failure_context(
                    error,
                    elapsed_s=elapsed_s,
                    attempt=attempt,
                    bridge_metrics=bridge_metrics,
                    will_retry=retryable_startup_error,
                )
                debug_tracer.log_debug(
                    event_type="provider_live_failure",
                    source="websocket",
                    session_id=session_id,
                    **failure_context,
                )

            if retryable_startup_error:
                logger.warning(
                    "Retrying ws_live startup after provider/live-path error session_id=%s attempt=%s elapsed_s=%.3f",
                    session_id,
                    attempt + 1,
                    elapsed_s,
                )
                await asyncio.sleep(_STARTUP_RETRY_BACKOFF_S)
                continue

            if _is_provider_live_path_error(error):
                logger.exception(
                    "Provider/live-path failure in ws_live session_id=%s classification=%s provider_error_code=%s elapsed_s=%.3f retry_context=%s bridge_health=%s",
                    session_id,
                    failure_context["classification"],
                    failure_context["provider_error_code"],
                    failure_context["elapsed_s"],
                    failure_context["retry_context"],
                    failure_context["bridge_health"],
                )
            else:
                logger.exception("Unhandled error in ws_live session_id=%s", session_id)
            await _safe_close(websocket, code=1011)
            return
