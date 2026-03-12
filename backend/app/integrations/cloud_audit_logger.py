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
    "child_quote_summary",
    "transcript_input",
    "transcript_output",
    "payload",  # depending on usage
    "audio_chunk",
}

@dataclasses.dataclass
class AuditEvent:
    session_id: str
    event_type: str
    metadata: dict[str, Any]
    timestamp: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        safe_metadata = {}
        for k, v in self.metadata.items():
            if k not in PII_FIELDS:
                safe_metadata[k] = v

        return {
            "session_id": self.session_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "metadata": safe_metadata,
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
    # Output as JSON for Cloud Logging parsing
    logger.info(json.dumps(event.to_dict()))
