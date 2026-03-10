"""Tests for clinical_session_store.py — WS2 store coverage."""

from __future__ import annotations

from app.services.clinical_session_store import (
    ClinicalSessionStore,
    get_clinical_session_store,
)


def test_register_session_creates_empty_state() -> None:
    store = ClinicalSessionStore()
    store.register_session("s1")
    assert store.has_session("s1")


def test_has_session_returns_false_for_unknown() -> None:
    store = ClinicalSessionStore()
    assert store.has_session("unknown") is False


def test_register_session_is_idempotent() -> None:
    store = ClinicalSessionStore()
    store.register_session("s1")
    store.add_alert("s1", {"emotion": "fear"})
    store.register_session("s1")  # must NOT reset existing data
    assert len(store.get_alerts("s1")) == 1


def test_add_alert_stores_alert_dict() -> None:
    store = ClinicalSessionStore()
    store.register_session("s1")
    store.add_alert("s1", {"primary_emotion": "anxiety", "risk_level": "medium"})
    alerts = store.get_alerts("s1")
    assert len(alerts) == 1
    assert alerts[0]["primary_emotion"] == "anxiety"


def test_add_alert_auto_registers_session() -> None:
    store = ClinicalSessionStore()
    store.add_alert("s2", {"emotion": "fear"})
    assert store.has_session("s2")
    assert len(store.get_alerts("s2")) == 1


def test_add_payload_stores_payload_dict() -> None:
    store = ClinicalSessionStore()
    store.register_session("s1")
    store.add_payload("s1", {"primary_emotion": "sadness", "trigger": "bullying"})
    insights = store.get_insights("s1")
    assert len(insights["payloads"]) == 1
    assert insights["payloads"][0]["primary_emotion"] == "sadness"


def test_add_summary_stores_string() -> None:
    store = ClinicalSessionStore()
    store.register_session("s1")
    store.add_summary("s1", "Child expressed fear about nightmares.")
    insights = store.get_insights("s1")
    assert len(insights["summaries"]) == 1
    assert "fear" in insights["summaries"][0]


def test_get_alerts_returns_copy() -> None:
    store = ClinicalSessionStore()
    store.add_alert("s1", {"emotion": "anger"})
    alerts = store.get_alerts("s1")
    alerts.append({"emotion": "mutated"})
    assert len(store.get_alerts("s1")) == 1


def test_get_alerts_returns_empty_for_unknown_session() -> None:
    store = ClinicalSessionStore()
    assert store.get_alerts("nonexistent") == []


def test_get_insights_returns_full_state() -> None:
    store = ClinicalSessionStore()
    store.register_session("s1")
    store.add_alert("s1", {"emotion": "fear"})
    store.add_payload("s1", {"key": "value"})
    store.add_summary("s1", "Summary text")
    insights = store.get_insights("s1")
    assert insights["session_id"] == "s1"
    assert len(insights["alerts"]) == 1
    assert len(insights["payloads"]) == 1
    assert len(insights["summaries"]) == 1


def test_get_insights_returns_empty_for_unknown_session() -> None:
    store = ClinicalSessionStore()
    insights = store.get_insights("nonexistent")
    assert insights["session_id"] == "nonexistent"
    assert insights["alerts"] == []
    assert insights["payloads"] == []
    assert insights["summaries"] == []


def test_multiple_alerts_accumulate() -> None:
    store = ClinicalSessionStore()
    store.register_session("s1")
    store.add_alert("s1", {"emotion": "fear"})
    store.add_alert("s1", {"emotion": "anger"})
    store.add_alert("s1", {"emotion": "sadness"})
    assert len(store.get_alerts("s1")) == 3


def test_add_alert_copies_dict_defensively() -> None:
    store = ClinicalSessionStore()
    original = {"emotion": "fear"}
    store.add_alert("s1", original)
    original["emotion"] = "mutated"
    assert store.get_alerts("s1")[0]["emotion"] == "fear"


def test_get_clinical_session_store_returns_singleton() -> None:
    store_a = get_clinical_session_store()
    store_b = get_clinical_session_store()
    assert store_a is store_b


def test_sessions_are_isolated() -> None:
    store = ClinicalSessionStore()
    store.add_alert("s1", {"emotion": "fear"})
    store.add_alert("s2", {"emotion": "anger"})
    assert len(store.get_alerts("s1")) == 1
    assert len(store.get_alerts("s2")) == 1
    assert store.get_alerts("s1")[0]["emotion"] == "fear"
    assert store.get_alerts("s2")[0]["emotion"] == "anger"
