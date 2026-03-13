"""Tests for clinical_extractor.py — WS3 store integration."""

from __future__ import annotations

import asyncio

import pytest

from app.services import clinical_extractor
from app.services.clinical_session_store import ClinicalSessionStore


def test_build_clinical_payload_maps_all_alert_fields() -> None:
    payload = clinical_extractor.build_clinical_payload(
        alert_payload={
            "primary_emotion": "anxiety",
            "trigger": "school",
            "recommended_strategy": "slow breathing",
            "risk_level": "medium",
            "child_quote_summary": "The monster felt nervous.",
        }
    )

    assert payload == {
        "primary_emotion": "anxiety",
        "trigger": "school",
        "recommended_strategy": "slow breathing",
        "risk_level": "medium",
        "child_quote_summary": "The monster felt nervous.",
        "transcript_input": [],
        "transcript_output": [],
    }


def test_build_clinical_payload_includes_transcript_snapshot_when_provided() -> None:
    payload = clinical_extractor.build_clinical_payload(
        alert_payload={"primary_emotion": "fear"},
        transcript_snapshot={"input": ["I am scared"], "output": ["You are safe here"]},
    )

    assert payload["transcript_input"] == ["I am scared"]
    assert payload["transcript_output"] == ["You are safe here"]


def test_build_clinical_summary_returns_english_string_with_emotion_and_risk() -> None:
    summary = clinical_extractor.build_clinical_summary(
        {
            "primary_emotion": "frustration",
            "trigger": "homework",
            "recommended_strategy": "take a short break",
            "risk_level": "low",
        }
    )

    assert "frustration" in summary
    assert "Risk level: low." in summary


@pytest.mark.asyncio
async def test_extract_and_log_completes_without_raising() -> None:
    await clinical_extractor.extract_and_log(
        alert_payload={"primary_emotion": "anxiety", "risk_level": "medium"},
        transcript_snapshot={"input": ["I feel nervous"], "output": []},
    )


@pytest.mark.asyncio
async def test_extract_and_log_swallows_exceptions_silently(monkeypatch, caplog) -> None:
    def _raise(*, alert_payload: dict, transcript_snapshot: dict | None = None) -> dict:
        _ = alert_payload, transcript_snapshot
        raise RuntimeError("boom")

    monkeypatch.setattr(clinical_extractor, "build_clinical_payload", _raise)

    with caplog.at_level("WARNING", logger="app.services.clinical_extractor"):
        await clinical_extractor.extract_and_log(alert_payload={"primary_emotion": "fear"})

    assert any("clinical_extractor failed silently" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_schedule_extraction_returns_task() -> None:
    task = clinical_extractor.schedule_extraction(alert_payload={"primary_emotion": "distress"})

    try:
        assert isinstance(task, asyncio.Task)
        await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# WS3 — Store write tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_and_log_writes_payload_and_summary_to_store(monkeypatch) -> None:
    """extract_and_log must persist payload + summary to clinical store when session_id is provided."""
    fake_store = ClinicalSessionStore()
    fake_store.register_session("s-test")
    monkeypatch.setattr(clinical_extractor, "get_clinical_session_store", lambda: fake_store)

    # Mock DLP to approve
    from app.services import dlp_gatekeeper
    async def _mock_redact(p, mode=None):
        return dlp_gatekeeper.DLPDecision(True, p, "ok")
    monkeypatch.setattr(dlp_gatekeeper, "inspect_and_redact", _mock_redact)

    await clinical_extractor.extract_and_log(
        alert_payload={"primary_emotion": "anxiety", "risk_level": "high"},
        session_id="s-test",
    )

    insights = fake_store.get_insights("s-test")
    assert len(insights["payloads"]) == 1
    assert insights["payloads"][0]["primary_emotion"] == "anxiety"
    assert len(insights["summaries"]) == 1
    assert "anxiety" in insights["summaries"][0]


@pytest.mark.asyncio
async def test_extract_and_log_discards_on_dlp_failure(monkeypatch, caplog) -> None:
    """If DLP rejects, payload must not be persisted to the store."""
    fake_store = ClinicalSessionStore()
    fake_store.register_session("s-test-dlp")
    monkeypatch.setattr(clinical_extractor, "get_clinical_session_store", lambda: fake_store)

    from app.services import dlp_gatekeeper
    async def _mock_redact(p, mode=None):
        return dlp_gatekeeper.DLPDecision(False, None, "dlp_redaction_discarded_policy")
    monkeypatch.setattr(dlp_gatekeeper, "inspect_and_redact", _mock_redact)

    with caplog.at_level("WARNING", logger="app.services.clinical_extractor"):
        await clinical_extractor.extract_and_log(
            alert_payload={"primary_emotion": "toxic", "risk_level": "high"},
            session_id="s-test-dlp",
        )

    # No writes to store
    insights = fake_store.get_insights("s-test-dlp")
    assert len(insights["payloads"]) == 0
    assert len(insights["summaries"]) == 0

    assert any("clinical_extraction_discarded" in record.message for record in caplog.records)



@pytest.mark.asyncio
async def test_extract_and_log_without_session_id_does_not_write_to_store(monkeypatch) -> None:
    """When session_id is None, no store writes should occur."""
    fake_store = ClinicalSessionStore()
    monkeypatch.setattr(clinical_extractor, "get_clinical_session_store", lambda: fake_store)

    await clinical_extractor.extract_and_log(
        alert_payload={"primary_emotion": "sadness"},
    )

    # No data should be in the store
    assert fake_store.get_insights("any")["payloads"] == []


@pytest.mark.asyncio
async def test_schedule_extraction_passes_session_id(monkeypatch) -> None:
    """schedule_extraction must forward session_id to extract_and_log."""
    fake_store = ClinicalSessionStore()
    fake_store.register_session("s-sched")
    monkeypatch.setattr(clinical_extractor, "get_clinical_session_store", lambda: fake_store)

    from app.services import dlp_gatekeeper
    async def _mock_redact(p, mode=None):
        return dlp_gatekeeper.DLPDecision(True, p, "ok")
    monkeypatch.setattr(dlp_gatekeeper, "inspect_and_redact", _mock_redact)

    task = clinical_extractor.schedule_extraction(
        alert_payload={"primary_emotion": "fear"},
        session_id="s-sched",
    )
    try:
        await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    insights = fake_store.get_insights("s-sched")
    assert len(insights["payloads"]) == 1


# ---------------------------------------------------------------------------
# emotional_state_current — WS-FinalMile: extractor must update store state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_and_log_updates_emotional_state_in_store(monkeypatch) -> None:
    """After successful extraction, store.set_emotional_state must reflect primary_emotion."""
    fake_store = ClinicalSessionStore()
    fake_store.register_session("s-emo-ex")
    monkeypatch.setattr(clinical_extractor, "get_clinical_session_store", lambda: fake_store)

    from app.services import dlp_gatekeeper

    async def _mock_redact(p, mode=None):
        return dlp_gatekeeper.DLPDecision(True, p, "ok")

    monkeypatch.setattr(dlp_gatekeeper, "inspect_and_redact", _mock_redact)

    await clinical_extractor.extract_and_log(
        alert_payload={"primary_emotion": "excited", "risk_level": "low"},
        session_id="s-emo-ex",
    )

    insights = fake_store.get_insights("s-emo-ex")
    assert insights["emotional_state_current"] == "excited"


@pytest.mark.asyncio
async def test_extract_and_log_dlp_discard_does_not_update_emotional_state(monkeypatch) -> None:
    """If DLP rejects, emotional_state_current must NOT be updated."""
    fake_store = ClinicalSessionStore()
    fake_store.register_session("s-emo-dlp")
    monkeypatch.setattr(clinical_extractor, "get_clinical_session_store", lambda: fake_store)

    from app.services import dlp_gatekeeper

    async def _mock_redact(p, mode=None):
        return dlp_gatekeeper.DLPDecision(False, None, "dlp_rejected")

    monkeypatch.setattr(dlp_gatekeeper, "inspect_and_redact", _mock_redact)

    await clinical_extractor.extract_and_log(
        alert_payload={"primary_emotion": "toxic"},
        session_id="s-emo-dlp",
    )

    # State must remain default "calm"
    insights = fake_store.get_insights("s-emo-dlp")
    assert insights["emotional_state_current"] == "calm"