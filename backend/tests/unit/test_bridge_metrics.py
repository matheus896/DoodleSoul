from __future__ import annotations

import time

from app.realtime.bridge_metrics import BridgeMetrics


def test_metrics_initial_state() -> None:
    m = BridgeMetrics()
    snap = m.snapshot()
    assert snap["upstream_audio_count"] == 0
    assert snap["upstream_text_count"] == 0
    assert snap["downstream_audio_count"] == 0
    assert snap["downstream_text_count"] == 0
    assert snap["errors"] == 0
    assert snap["elapsed_seconds"] >= 0


def test_metrics_record_upstream_audio() -> None:
    m = BridgeMetrics()
    m.record_upstream_audio(3200)
    m.record_upstream_audio(1600)

    assert m.upstream_audio_count == 2
    assert m.upstream_bytes_total == 4800


def test_metrics_record_upstream_text() -> None:
    m = BridgeMetrics()
    m.record_upstream_text()
    m.record_upstream_text()
    m.record_upstream_text()

    assert m.upstream_text_count == 3


def test_metrics_record_downstream() -> None:
    m = BridgeMetrics()
    m.record_downstream_audio(2400)
    m.record_downstream_text()

    assert m.downstream_audio_count == 1
    assert m.downstream_bytes_total == 2400
    assert m.downstream_text_count == 1


def test_metrics_record_errors() -> None:
    m = BridgeMetrics()
    m.record_error()
    m.record_error()

    assert m.errors == 2


def test_metrics_elapsed_time() -> None:
    m = BridgeMetrics(start_time=time.monotonic() - 5.0)
    assert m.elapsed_seconds >= 4.9


def test_snapshot_is_dict() -> None:
    m = BridgeMetrics()
    m.record_upstream_audio(100)
    m.record_downstream_text()
    snap = m.snapshot()

    assert isinstance(snap, dict)
    assert set(snap.keys()) == {
        "upstream_audio_count",
        "upstream_text_count",
        "upstream_bytes_total",
        "downstream_audio_count",
        "downstream_text_count",
        "downstream_bytes_total",
        "errors",
        "elapsed_seconds",
    }
