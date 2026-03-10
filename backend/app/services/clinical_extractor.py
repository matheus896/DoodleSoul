from __future__ import annotations

import asyncio
import logging
from typing import Any

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


async def extract_and_log(*, alert_payload: dict, transcript_snapshot: dict | None = None) -> None:
    try:
        payload = build_clinical_payload(
            alert_payload=alert_payload,
            transcript_snapshot=transcript_snapshot,
        )
        summary = build_clinical_summary(payload)
        logger.info("clinical_extraction session_payload=%s summary=%r", payload, summary)
    except Exception:
        logger.warning("clinical_extractor failed silently", exc_info=True)


def schedule_extraction(*, alert_payload: dict, transcript_snapshot: dict | None = None) -> asyncio.Task:
    return asyncio.create_task(
        extract_and_log(
            alert_payload=alert_payload,
            transcript_snapshot=transcript_snapshot,
        )
    )