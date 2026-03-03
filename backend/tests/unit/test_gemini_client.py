"""Tests for gemini_client.py — ADK tool stubs and function-call translation."""
from __future__ import annotations

from app.services.gemini_client import (
    AdkGeminiLiveStream,
    generate_image,
    generate_video,
)


# ---------------------------------------------------------------------------
# Tool stub tests
# ---------------------------------------------------------------------------


def test_generate_image_stub_returns_acknowledgment() -> None:
    result = generate_image(scene_id="scene-1", prompt="a blue robot")
    assert result["status"] == "acknowledged"
    assert result["scene_id"] == "scene-1"


def test_generate_image_stub_with_image_prompt_kwarg() -> None:
    result = generate_image(scene_id="scene-2", image_prompt="a red dragon")
    assert result["status"] == "acknowledged"
    assert result["scene_id"] == "scene-2"


def test_generate_video_stub_returns_acknowledgment() -> None:
    result = generate_video(scene_id="scene-1", prompt="robot walking")
    assert result["status"] == "acknowledged"
    assert result["scene_id"] == "scene-1"


def test_generate_video_stub_with_video_prompt_kwarg() -> None:
    result = generate_video(scene_id="scene-3", video_prompt="dragon flying")
    assert result["status"] == "acknowledged"
    assert result["scene_id"] == "scene-3"


# ---------------------------------------------------------------------------
# _translate_function_calls tests
# ---------------------------------------------------------------------------


def test_translate_empty_actions_returns_nothing() -> None:
    dumped: dict = {"invocation_id": "x", "author": "model"}
    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert result == []


def test_translate_empty_requested_function_calls_returns_nothing() -> None:
    dumped: dict = {"actions": {"requested_function_calls": []}}
    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert result == []


def test_translate_generate_image_call() -> None:
    dumped: dict = {
        "actions": {
            "requested_function_calls": [
                {"name": "generate_image", "args": {"scene_id": "scene-1", "image_prompt": "robot"}, "id": "call-1"},
            ]
        }
    }
    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert len(result) == 1
    ev = result[0]
    assert ev["type"] == "tool_call"
    assert ev["tool"] == "generate_image"
    assert ev["args"]["image_prompt"] == "robot"
    assert ev["scene_id"] == "scene-1"


def test_translate_scene_id_promoted_to_top_level() -> None:
    dumped: dict = {
        "actions": {
            "requested_function_calls": [
                {"name": "generate_video", "args": {"scene_id": "scene-2", "video_prompt": "flying"}, "id": "call-2"},
            ]
        }
    }
    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert result[0]["scene_id"] == "scene-2"
    assert result[0]["tool"] == "generate_video"


def test_translate_missing_scene_id_defaults_to_empty_string() -> None:
    dumped: dict = {
        "actions": {
            "requested_function_calls": [
                {"name": "generate_image", "args": {"image_prompt": "cat"}, "id": "call-3"},
            ]
        }
    }
    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert result[0]["scene_id"] == ""


def test_translate_skips_entries_without_name() -> None:
    dumped: dict = {
        "actions": {
            "requested_function_calls": [
                {"name": "", "args": {}, "id": "call-4"},
                {"args": {}, "id": "call-5"},  # name key absent
            ]
        }
    }
    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert result == []


def test_translate_multiple_calls_returned_in_order() -> None:
    dumped: dict = {
        "actions": {
            "requested_function_calls": [
                {"name": "generate_image", "args": {"scene_id": "scene-1"}, "id": "call-A"},
                {"name": "generate_video", "args": {"scene_id": "scene-2"}, "id": "call-B"},
            ]
        }
    }
    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert len(result) == 2
    assert result[0]["tool"] == "generate_image"
    assert result[1]["tool"] == "generate_video"


def test_translate_non_dict_entries_skipped() -> None:
    dumped: dict = {
        "actions": {
            "requested_function_calls": [
                "not-a-dict",
                None,
                {"name": "generate_image", "args": {"scene_id": "scene-1"}, "id": "call-X"},
            ]
        }
    }
    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert len(result) == 1
    assert result[0]["tool"] == "generate_image"


def test_translate_args_json_string_parsed() -> None:
    dumped: dict = {
        "actions": {
            "requested_function_calls": [
                {
                    "name": "generate_image",
                    "args": '{"scene_id":"scene-json","image_prompt":"moon"}',
                    "id": "call-json",
                },
            ]
        }
    }

    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert len(result) == 1
    assert result[0]["scene_id"] == "scene-json"
    assert result[0]["args"]["image_prompt"] == "moon"


def test_translate_arguments_key_supported() -> None:
    dumped: dict = {
        "actions": {
            "requested_function_calls": [
                {
                    "name": "generate_video",
                    "arguments": {"scene_id": "scene-args-key", "video_prompt": "walk"},
                    "id": "call-arguments",
                },
            ]
        }
    }

    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert len(result) == 1
    assert result[0]["scene_id"] == "scene-args-key"
    assert result[0]["args"]["video_prompt"] == "walk"


def test_translate_text_tool_marker_generate_image() -> None:
    dumped: dict = {
        "content": {
            "parts": [
                {
                    "text": (
                        "[ANIMISM_TOOL_CALL] "
                        '{"tool":"generate_image","args":{"scene_id":"scene-t1","image_prompt":"a kite"}}'
                    )
                }
            ]
        }
    }

    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert len(result) == 1
    assert result[0]["tool"] == "generate_image"
    assert result[0]["scene_id"] == "scene-t1"
    assert result[0]["args"]["image_prompt"] == "a kite"


def test_translate_text_tool_marker_ignored_when_invalid_json() -> None:
    dumped: dict = {
        "content": {
            "parts": [
                {
                    "text": "[ANIMISM_TOOL_CALL] {invalid-json"
                }
            ]
        }
    }

    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert result == []


def test_translate_text_tool_marker_from_output_transcription() -> None:
    dumped: dict = {
        "output_transcription": {
            "text": (
                "[ANIMISM_TOOL_CALL] "
                '{"tool":"generate_video","args":{"scene_id":"scene-t2","video_prompt":"gentle motion"}}'
            ),
            "finished": False,
        }
    }

    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert len(result) == 1
    assert result[0]["tool"] == "generate_video"
    assert result[0]["scene_id"] == "scene-t2"
    assert result[0]["args"]["video_prompt"] == "gentle motion"


def test_translate_text_tool_marker_inline_multiple_calls() -> None:
    dumped: dict = {
        "output_transcription": {
            "text": (
                "Let's draw now. "
                "[ANIMISM_TOOL_CALL] {\"tool\":\"generate_image\",\"args\":{\"scene_id\":\"scene-t3\",\"image_prompt\":\"forest\"}} "
                "And animate it. "
                "[ANIMISM_TOOL_CALL] {\"tool\":\"generate_video\",\"args\":{\"scene_id\":\"scene-t3\",\"video_prompt\":\"forest wind\"}}"
            ),
            "finished": True,
        }
    }

    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert len(result) == 2
    assert result[0]["tool"] == "generate_image"
    assert result[1]["tool"] == "generate_video"
