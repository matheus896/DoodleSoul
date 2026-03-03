from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _is_parser_accepted(event: dict[str, Any]) -> bool:
    event_type = event.get("type")
    scene_id = event.get("scene_id")
    if not isinstance(event_type, str) or not isinstance(scene_id, str) or not scene_id:
        return False

    if event_type == "drawing_in_progress":
        return True
    if event_type == "media.image.created":
        return (
            isinstance(event.get("url"), str)
            and isinstance(event.get("width"), int)
            and isinstance(event.get("height"), int)
        )
    if event_type == "media_delayed":
        return isinstance(event.get("elapsed_seconds"), (int, float))
    if event_type == "media.video.created":
        return (
            isinstance(event.get("url"), str)
            and isinstance(event.get("duration_seconds"), (int, float))
        )
    return False


def _timeline_reduce(events: list[dict[str, Any]], scene_id: str) -> str:
    status = "unknown"
    for event in events:
        if event.get("scene_id") != scene_id:
            continue
        event_type = event.get("type")
        if event_type == "drawing_in_progress":
            status = "generating"
        elif event_type == "media.image.created":
            status = "image_ready"
        elif event_type == "media_delayed":
            status = "delayed"
        elif event_type == "media.video.created":
            status = "video_ready"
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Scenario 3 probe events against frontend contract checks")
    parser.add_argument("--probe", default="A:/hackaton-google/tests/output/scenario3_adk_probe_events_textfallback_long.json")
    parser.add_argument("--output", default="A:/hackaton-google/tests/output/scenario3_frontend_contract_summary.json")
    args = parser.parse_args()

    probe = json.loads(Path(args.probe).read_text(encoding="utf-8"))
    media_events = [
        event for event in (probe.get("media_related_events") or [])
        if isinstance(event, dict) and event.get("type") != "tool_call"
    ]

    parser_acceptance = all(_is_parser_accepted(event) for event in media_events)
    scene_candidates = [
        event.get("scene_id")
        for event in media_events
        if isinstance(event.get("scene_id"), str) and event.get("scene_id")
    ]
    scene_id = scene_candidates[0] if scene_candidates else ""
    final_status = _timeline_reduce(media_events, scene_id) if scene_id else "unknown"

    output = {
        "scene_id": scene_id,
        "media_events": media_events,
        "checks": {
            "frontend_parser_acceptance_equivalent": parser_acceptance,
            "timeline_reaches_video_ready_equivalent": final_status == "video_ready",
        },
        "final_timeline_status": final_status,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print("[scenario3_frontend_contract_replay] checks:")
    for key, value in output["checks"].items():
        print(f"  - {key}: {value}")
    print(f"[scenario3_frontend_contract_replay] output={output_path}")


if __name__ == "__main__":
    main()
