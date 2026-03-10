from __future__ import annotations

import asyncio

import pytest

from app.services import clinical_extractor


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