"""Cloud Audit Logger integration for immutable, safe evidence (Story 5.3)."""

from __future__ import annotations

import dataclasses
import datetime
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Fields known to contain strings that might be PII, and should NEVER be in audit logs
PII_FIELDS = {
    "child_name",
    "child_context",
    "child_quote_summary",
    "transcript_input",
    "transcript_output",
    "payload",  # depending on usage
    "audio_chunk",
}

SCHEMA_VERSION = "1.0"


def _sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        safe_dict: dict[str, Any] = {}
        for key, nested_value in value.items():
            if key in PII_FIELDS:
                continue
            safe_dict[key] = _sanitize_metadata(nested_value)
        return safe_dict
    if isinstance(value, list):
        return [_sanitize_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_metadata(item) for item in value]
    return value

@dataclasses.dataclass
class AuditEvent:
    session_id: str
    event_type: str
    metadata: dict[str, Any]
    timestamp: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "metadata": _sanitize_metadata(self.metadata),
        }


def emit_audit_event(session_id: str, event_type: str, metadata: dict[str, Any] | None = None) -> None:
    """
    Produce a canonical structured audit log.
    Ensures PII fields are stripped before emitting to standard out/Cloud Logging.
    """
    event = AuditEvent(
        session_id=session_id,
        event_type=event_type,
        metadata=metadata or {},
    )
    # print() writes to sys.stdout so Cloud Logging captures it as pure JSON (jsonPayload).
    # logger.info() would add the app-level text formatter prefix, creating textPayload instead.
    print(json.dumps(event.to_dict()), flush=True)
