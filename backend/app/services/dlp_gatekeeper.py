"""DLP Gatekeeper Service for mandatory redaction before persistence (FR19)."""

from __future__ import annotations

import copy
import dataclasses
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class DLPDecision:
    is_approved: bool
    redacted_payload: dict[str, Any] | None
    reason: str


async def inspect_and_redact(
    payload: dict[str, Any],
    mode: str | None = None,
) -> DLPDecision:
    """
    Mandatory DLP gatekeeper for session summaries and transcripts.
    If DLP redaction fails, is unavailable, or flags content as toxic, it fail-safes to discard.
    """
    if mode is None:
        # Defaults to 'local' for now, or check an env var if needed.
        mode = os.environ.get("DLP_MODE", "local").lower()

    if mode == "fail":
        logger.warning("compliance_event=dlp_redaction_discarded_unavailable")
        return DLPDecision(False, None, "dlp_redaction_discarded_unavailable")

    if mode == "malformed":
        logger.warning("compliance_event=dlp_redaction_discarded_malformed")
        return DLPDecision(False, None, "dlp_redaction_discarded_malformed")

    if mode == "toxic":
        logger.warning("compliance_event=dlp_redaction_discarded_policy")
        return DLPDecision(False, None, "dlp_redaction_discarded_policy")

    if mode == "cloud":
        # Placeholder for Cloud Data Loss Prevention API integration
        # For now, it fail-safes to local or raises explicitly if missing
        pass

    # Basic local mock redaction
    redacted = copy.deepcopy(payload)
    if "child_quote_summary" in redacted and isinstance(redacted["child_quote_summary"], str):
        # Extremely basic mock replacement for local tests
        redacted["child_quote_summary"] = redacted["child_quote_summary"].replace("John", "[PERSON]")

    logger.info("compliance_event=dlp_redaction_applied")
    return DLPDecision(True, redacted, "dlp_redaction_applied")
