"""Tests for DLP gatekeeper fail-safe discard (Story 5.1)."""

from __future__ import annotations

import pytest

from app.services import dlp_gatekeeper


def test_dlp_decision_dataclass() -> None:
    decision = dlp_gatekeeper.DLPDecision(
        is_approved=True,
        redacted_payload={"safe": "data"},
        reason="Redaction applied successfully",
    )
    assert decision.is_approved is True
    assert decision.redacted_payload == {"safe": "data"}


@pytest.mark.asyncio
async def test_inspect_and_redact_success() -> None:
    # In local mode, should just pass through or apply minimal mock redaction
    payload = {"primary_emotion": "anxiety", "child_quote_summary": "I am John"}
    decision = await dlp_gatekeeper.inspect_and_redact(payload, mode="local")
    
    assert decision.is_approved is True
    assert decision.redacted_payload is not None
    # For local mode, we might just redact "John" to "[PERSON]" or leave it, but it shouldn't discard
    assert decision.reason == "dlp_redaction_applied"


@pytest.mark.asyncio
async def test_inspect_and_redact_unavailability() -> None:
    # If the underlying service fails (or mode is simulated failure)
    payload = {"primary_emotion": "anxiety", "trigger": "simulate_dlp_failure"}
    decision = await dlp_gatekeeper.inspect_and_redact(payload, mode="fail")

    assert decision.is_approved is False
    assert decision.redacted_payload is None
    assert decision.reason == "dlp_redaction_discarded_unavailable"


@pytest.mark.asyncio
async def test_inspect_and_redact_malformed_response() -> None:
    # If DLP returns something unexpected, we fail-safe discard
    payload = {"primary_emotion": "anxiety", "trigger": "simulate_dlp_malformed"}
    decision = await dlp_gatekeeper.inspect_and_redact(payload, mode="malformed")

    assert decision.is_approved is False
    assert decision.redacted_payload is None
    assert decision.reason == "dlp_redaction_discarded_malformed"


@pytest.mark.asyncio
async def test_inspect_and_redact_explicit_discard() -> None:
    # Sometimes DLP explicitly says this is too toxic/dangerous to store at all
    payload = {"primary_emotion": "anxiety", "trigger": "simulate_dlp_toxic"}
    decision = await dlp_gatekeeper.inspect_and_redact(payload, mode="toxic")

    assert decision.is_approved is False
    assert decision.redacted_payload is None
    assert decision.reason == "dlp_redaction_discarded_policy"
