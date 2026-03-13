"""Tests for immutable audit and reproducible evidence (Story 5.3)."""

from __future__ import annotations

import json

from app.integrations import cloud_audit_logger


def test_audit_event_schema_removes_pii() -> None:
    # Given an event that contains PII in raw fields
    metadata = {
        "risk_level": "none",
        "primary_emotion": "calm",
        "child_quote_summary": "I hate everything", # Potential PII
        "transcript_input": ["bad words"],           # PII
        "transcript_output": ["calm down"],          # PII
        "reason": "dlp_redaction_applied",
    }
    
    event = cloud_audit_logger.AuditEvent(
        session_id="s-test-audit",
        event_type="clinical_alert_stored",
        metadata=metadata,
    )
    
    # When dumping to log
    payload = event.to_dict()
    
    # Then session_id and type are retained
    assert payload["schema_version"] == cloud_audit_logger.SCHEMA_VERSION
    assert payload["session_id"] == "s-test-audit"
    assert payload["event_type"] == "clinical_alert_stored"
    assert "timestamp" in payload
    
    # And NO PII fields leak into metadata
    safe_meta = payload["metadata"]
    assert "risk_level" in safe_meta
    assert "child_quote_summary" not in safe_meta
    assert "transcript_input" not in safe_meta
    assert "transcript_output" not in safe_meta
    assert safe_meta.get("reason") == "dlp_redaction_applied"


def test_audit_event_schema_removes_nested_pii() -> None:
    event = cloud_audit_logger.AuditEvent(
        session_id="s-test-nested",
        event_type="session_started",
        metadata={
            "safe": "value",
            "child_context": {"child_name": "Leo"},
            "details": {
                "tool_mode": "text_fallback",
                "transcript_output": ["secret"],
            },
            "events": [
                {"name": "ok", "payload": "should_drop"},
                {"name": "ok2", "level": "info"},
            ],
        },
    )

    payload = event.to_dict()
    assert payload["metadata"]["safe"] == "value"
    assert "child_context" not in payload["metadata"]
    assert payload["metadata"]["details"]["tool_mode"] == "text_fallback"
    assert "transcript_output" not in payload["metadata"]["details"]
    assert payload["metadata"]["events"][0]["name"] == "ok"
    assert "payload" not in payload["metadata"]["events"][0]


def test_emit_audit_event_logs_json(caplog) -> None:
    with caplog.at_level("INFO", logger="app.integrations.cloud_audit_logger"):
        cloud_audit_logger.emit_audit_event(
            session_id="s-123",
            event_type="safety.pivot.triggered",
            metadata={"trigger": "bad_topic", "action": "interrupt"}
        )
        
    assert len(caplog.records) == 1
    record = caplog.records[0]
    
    # Log message should be parseable JSON
    data = json.loads(record.message)
    assert data["session_id"] == "s-123"
    assert data["event_type"] == "safety.pivot.triggered"
    assert data["metadata"]["action"] == "interrupt"
