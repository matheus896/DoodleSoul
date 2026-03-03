from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEBUG_PATTERN = re.compile(
    r"\[ANIMISM_DEBUG\]\[(?P<source>[^\]]+)\]\s+"
    r"event_type=(?P<event_type>\S+)\s+"
    r"scene_id=(?P<scene_id>\S+)\s+"
    r"session_id=(?P<session_id>\S+)\s+"
    r"ts=(?P<ts>\d+)"
)


def _load_probe(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_backend_hits(log_path: Path, scene_id: str | None) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[ANIMISM_DEBUG]" not in line:
            continue
        match = DEBUG_PATTERN.search(line)
        if not match:
            continue
        payload = match.groupdict()
        current_scene = payload.get("scene_id")
        if scene_id and current_scene not in {scene_id, "-"}:
            continue
        payload["line"] = line
        hits.append(payload)
    return hits


def main() -> None:
    parser = argparse.ArgumentParser(description="Correlate Scenario 3 ADK probe events with backend debug logs")
    parser.add_argument("--probe", default="A:/hackaton-google/tests/output/scenario3_adk_probe_events.json")
    parser.add_argument("--backend-log", default="A:/hackaton-google/tests/output/scenario3_adk_backend.log")
    parser.add_argument("--output", default="A:/hackaton-google/tests/output/scenario3_adk_evidence_summary.json")
    args = parser.parse_args()

    probe_path = Path(args.probe)
    backend_log_path = Path(args.backend_log)
    output_path = Path(args.output)

    probe = _load_probe(probe_path)

    media_related = probe.get("media_related_events") or []
    scene_candidates = [
        e.get("scene_id") for e in media_related
        if isinstance(e, dict) and isinstance(e.get("scene_id"), str) and e.get("scene_id")
    ]
    scene_id = scene_candidates[0] if scene_candidates else None

    backend_hits = _extract_backend_hits(backend_log_path, scene_id)

    backend_event_types = [hit["event_type"] for hit in backend_hits]
    probe_event_types = [
        e.get("type") for e in media_related
        if isinstance(e, dict) and isinstance(e.get("type"), str)
    ]

    summary = {
        "session_id": probe.get("session_id"),
        "scene_id": scene_id,
        "probe_event_types": probe_event_types,
        "backend_event_types": backend_event_types,
        "checks": {
            "tool_call_recognized": "tool_call_recognized" in backend_event_types,
            "scene_orchestration_started": "scene_orchestration_started" in backend_event_types,
            "media_event_emitted": "media_event_emitted" in backend_event_types,
            "frontend_parser_ready_events_present": any(
                t in {"drawing_in_progress", "media.image.created", "media_delayed", "media.video.created"}
                for t in probe_event_types
            ),
        },
        "probe_equivalence": {
            "tool_call_present": any(t == "tool_call" for t in probe_event_types),
            "orchestration_started_equivalent": any(t == "drawing_in_progress" for t in probe_event_types),
            "media_emitted_equivalent": any(
                t in {"media.image.created", "media_delayed", "media.video.created"}
                for t in probe_event_types
            ),
        },
        "backend_hits": backend_hits,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"[extract_scenario3_evidence] scene_id={scene_id}")
    print("[extract_scenario3_evidence] checks:")
    for key, value in summary["checks"].items():
        print(f"  - {key}: {value}")
    print(f"[extract_scenario3_evidence] output={output_path}")


if __name__ == "__main__":
    main()
