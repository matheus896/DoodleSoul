from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.clinical_session_store import get_clinical_session_store

logger = logging.getLogger(__name__)


def build_clinical_payload(*, alert_payload: dict, transcript_snapshot: dict | None = None) -> dict[str, Any]:
    snapshot = transcript_snapshot or {}
    return {
        "primary_emotion": alert_payload.get("primary_emotion", "unknown"),
        "trigger": alert_payload.get("trigger", ""),
        "recommended_strategy": alert_payload.get("recommended_strategy", ""),
        "risk_level": alert_payload.get("risk_level", "low"),
        "child_quote_summary": alert_payload.get("child_quote_summary", ""),
        "transcript_input": list(snapshot.get("input", [])),
        "transcript_output": list(snapshot.get("output", [])),
    }


def build_clinical_summary(payload: dict[str, Any]) -> str:
    emotion = payload.get("primary_emotion", "unknown")
    trigger = payload.get("trigger", "")
    strategy = payload.get("recommended_strategy", "")
    risk = payload.get("risk_level", "low")
    return (
        f"Clinical observation: The child expressed {emotion}. "
        f"Trigger: {trigger}. "
        f"Recommended strategy: {strategy}. "
        f"Risk level: {risk}."
    )


from app.services import dlp_gatekeeper

async def extract_and_log(
    *,
    alert_payload: dict,
    transcript_snapshot: dict | None = None,
    session_id: str | None = None,
) -> None:
    try:
        payload = build_clinical_payload(
            alert_payload=alert_payload,
            transcript_snapshot=transcript_snapshot,
        )

        decision = await dlp_gatekeeper.inspect_and_redact(payload)
        if not decision.is_approved:
            logger.warning(
                "clinical_extraction_discarded session_id=%s reason=%s",
                session_id or "unknown",
                decision.reason,
            )
            from app.integrations import cloud_audit_logger
            cloud_audit_logger.emit_audit_event(
                session_id=session_id or "unknown",
                event_type="dlp_redaction_discarded",
                metadata={"reason": decision.reason}
            )
            return

        redacted_payload = decision.redacted_payload or {}
        summary = build_clinical_summary(redacted_payload)

        # WS3 — persist to clinical store when session_id is available
        if session_id is not None:
            store = get_clinical_session_store()
            store.add_payload(session_id, redacted_payload)
            store.add_summary(session_id, summary)
            store.set_emotional_state(session_id, redacted_payload.get("primary_emotion", "calm"))

        # WS5 — Tier 1 structured observability
        logger.info(
            "clinical_extraction_completed session_id=%s",
            session_id or "unknown",
        )
        from app.integrations import cloud_audit_logger
        cloud_audit_logger.emit_audit_event(
            session_id=session_id or "unknown",
            event_type="dlp_redaction_applied",
            metadata={"reason": decision.reason}
        )
    except Exception:
        logger.warning("clinical_extractor failed silently", exc_info=True)


def schedule_extraction(
    *,
    alert_payload: dict,
    transcript_snapshot: dict | None = None,
    session_id: str | None = None,
) -> asyncio.Task:
    # WS5 — Tier 1 structured observability
    logger.info(
        "clinical_extraction_scheduled session_id=%s",
        session_id or "unknown",
    )
    return asyncio.create_task(
        extract_and_log(
            alert_payload=alert_payload,
            transcript_snapshot=transcript_snapshot,
            session_id=session_id,
        )
    )