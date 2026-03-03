"""Debug tracer — single debug contract for Epic 3 observability.

Provides a toggle-gated structured logger that correlates events across
the backend pipeline using a common envelope:
    session_id, scene_id, event_type, source, timestamp_ms.

Toggle: set env var ``ANIMISM_DEBUG_MEDIA=1`` (or ``true`` / ``yes``) to
enable.  Off by default so normal runs are not polluted.

This module has no dependency on bridge, audio, or WebSocket code — it
is a pure utility consumed by interceptor, orchestrator, and optionally
bridge.

Logging policy: only metadata and event envelopes are logged.
Raw audio bytes and PII are explicitly excluded.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------

def is_debug_enabled() -> bool:
    """Return True when ``ANIMISM_DEBUG_MEDIA`` is set to a truthy value."""
    return os.getenv("ANIMISM_DEBUG_MEDIA", "").lower() in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Structured log helper
# ---------------------------------------------------------------------------

def log_debug(
    *,
    event_type: str,
    source: str,
    scene_id: str | None = None,
    session_id: str | None = None,
    **extra: Any,
) -> None:
    """Emit a structured debug log entry if the debug toggle is enabled.

    Parameters
    ----------
    event_type:
        Machine-readable discriminator for the log entry (e.g.
        ``"tool_call_recognized"``, ``"media_event_emitted"``).
    source:
        Component emitting the log (e.g. ``"interceptor"``,
        ``"orchestrator"``, ``"bridge"``).
    scene_id:
        Scene identifier (``None`` if not applicable).
    session_id:
        Session identifier (``None`` if not established at log point).
    **extra:
        Additional key-value metadata.  Must not contain raw audio bytes
        or personally identifiable information.
    """
    if not is_debug_enabled():
        return

    timestamp_ms = int(time.monotonic() * 1000)
    extra_str = " ".join(f"{k}={v!r}" for k, v in extra.items()) if extra else ""

    logger.info(
        "[ANIMISM_DEBUG][%s] event_type=%s scene_id=%s session_id=%s ts=%d %s",
        source,
        event_type,
        scene_id or "-",
        session_id or "-",
        timestamp_ms,
        extra_str,
    )
