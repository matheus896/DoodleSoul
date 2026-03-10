"""Tests for gemini_client.py — ADK tool stubs and function-call translation."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.gemini_client import (
    AdkGeminiLiveStream,
    GeminiLiveClient,
    build_agent_instruction,
    build_live_run_config,
    build_safety_config,
    generate_image,
    generate_video,
    report_clinical_alert,
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


def test_generate_image_stub_accepts_visual_context_fields() -> None:
    result = generate_image(
        scene_id="scene-ctx",
        image_prompt="a blue robot with round eyes",
        visual_traits=["blue", "round eyes"],
        child_context="friend from drawing",
    )
    assert result["status"] == "acknowledged"
    assert result["scene_id"] == "scene-ctx"


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


def test_build_live_run_config_uses_current_default_vad_behavior() -> None:
    created_audio_configs: list[object] = []

    class FakeAudioTranscriptionConfig:
        def __init__(self) -> None:
            created_audio_configs.append(self)

    class FakeRunConfig:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    fake_types = SimpleNamespace(
        Modality=SimpleNamespace(AUDIO="audio"),
        AudioTranscriptionConfig=FakeAudioTranscriptionConfig,
    )

    config = build_live_run_config(
        run_config_cls=FakeRunConfig,
        streaming_mode_bidi="bidi-mode",
        types_module=fake_types,
    )

    assert config.kwargs["streaming_mode"] == "bidi-mode"
    assert config.kwargs["response_modalities"] == ["audio"]
    assert len(created_audio_configs) == 2
    assert config.kwargs["output_audio_transcription"] is created_audio_configs[0]
    assert config.kwargs["input_audio_transcription"] is created_audio_configs[1]
    assert "realtime_input_config" not in config.kwargs


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


def test_build_agent_instruction_enforces_permission_and_single_story_policy() -> None:
    instruction = build_agent_instruction(native_tools_enabled=True)

    assert "ask for explicit permission" in instruction
    assert "at most one story generation cycle" in instruction
    assert "must include visual_traits and child_context" in instruction
    assert "wait for the system to confirm the image is ready" in instruction
    assert "must call generate_video as a separate step" in instruction


def test_build_agent_instruction_includes_text_tool_fallback_when_disabled() -> None:
    instruction = build_agent_instruction(native_tools_enabled=False)

    assert "[ANIMISM_TOOL_CALL]" in instruction
    assert '"tool":"generate_image"' in instruction


def test_build_agent_instruction_is_deterministic_without_persona_data() -> None:
    instruction_a = build_agent_instruction(native_tools_enabled=True, persona_data=None)
    instruction_b = build_agent_instruction(native_tools_enabled=True, persona_data=None)
    assert instruction_a == instruction_b
    assert "You are Animism" in instruction_a


def test_build_agent_instruction_replaces_identity_when_persona_provided() -> None:
    persona_data = {
        "personality_traits": ["curious", "kind"],
        "voice_traits": ["playful", "friendly"],
        "greeting_text": "Hi Luna, I'm your friend from the drawing!",
    }
    instruction = build_agent_instruction(native_tools_enabled=True, persona_data=persona_data)

    assert instruction.startswith("You are a magical imaginary friend")
    assert "You are Animism" not in instruction
    assert "curious, kind" in instruction
    assert "playful, friendly" in instruction
    assert "Hi Luna, I'm your friend from the drawing!" in instruction
    assert "Never break this character" in instruction


def test_build_agent_instruction_persona_identity_comes_before_rules() -> None:
    persona_data = {
        "personality_traits": ["brave"],
        "voice_traits": ["gentle"],
        "greeting_text": "Hello!",
    }
    instruction = build_agent_instruction(native_tools_enabled=True, persona_data=persona_data)

    identity_pos = instruction.index("magical imaginary friend")
    rules_pos = instruction.index("ask for explicit permission")
    assert identity_pos < rules_pos


def test_build_agent_instruction_persona_with_text_fallback() -> None:
    persona_data = {
        "personality_traits": ["brave"],
        "voice_traits": ["gentle"],
        "greeting_text": "Hello!",
    }
    instruction = build_agent_instruction(native_tools_enabled=False, persona_data=persona_data)

    assert "magical imaginary friend" in instruction
    assert "[ANIMISM_TOOL_CALL]" in instruction


# ---------------------------------------------------------------------------
# Conversational Spark tests
# ---------------------------------------------------------------------------


class FakeStream:
    def __init__(self) -> None:
        self.sent_texts: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent_texts.append(text)


@pytest.mark.asyncio
async def test_open_stream_sends_spark_when_persona_data_present() -> None:
    fake_stream = FakeStream()

    async def _factory(*, model: str, session_id: str):
        return fake_stream

    client = GeminiLiveClient(
        model="test-model",
        stream_factory=_factory,
        persona_data={"greeting_text": "Hi friend!"},
    )
    result = await client.open_stream("s1")

    assert result is fake_stream
    assert len(fake_stream.sent_texts) == 1
    assert "Hi friend!" in fake_stream.sent_texts[0]


@pytest.mark.asyncio
async def test_open_stream_does_not_send_spark_without_persona_data() -> None:
    fake_stream = FakeStream()

    async def _factory(*, model: str, session_id: str):
        return fake_stream

    client = GeminiLiveClient(model="test-model", stream_factory=_factory)
    result = await client.open_stream("s2")

    assert result is fake_stream
    assert fake_stream.sent_texts == []


# ---------------------------------------------------------------------------
# Epic 4 — report_clinical_alert stub tests
# ---------------------------------------------------------------------------


def test_report_clinical_alert_stub_returns_received() -> None:
    result = report_clinical_alert(
        primary_emotion="anxiety",
        trigger="school conflict",
        recommended_strategy="grounding exercise",
        risk_level="moderate",
        child_quote_summary="the monster was sad at school",
    )
    assert result["status"] == "received"
    assert result["primary_emotion"] == "anxiety"


def test_report_clinical_alert_stub_preserves_emotion_field() -> None:
    result = report_clinical_alert(
        primary_emotion="frustration",
        trigger="drawing difficulty",
        recommended_strategy="validation",
        risk_level="low",
        child_quote_summary="the monster couldn't do it",
    )
    assert result["primary_emotion"] == "frustration"
    assert result["status"] == "received"


# ---------------------------------------------------------------------------
# Epic 4 — build_safety_config tests
# ---------------------------------------------------------------------------


def test_build_safety_config_returns_four_settings() -> None:
    created: list[dict] = []

    class FakeSafetySetting:
        def __init__(self, *, category: str, threshold: str) -> None:
            created.append({"category": category, "threshold": threshold})

    fake_types = SimpleNamespace(
        HarmCategory=SimpleNamespace(
            HARM_CATEGORY_HARASSMENT="harassment",
            HARM_CATEGORY_HATE_SPEECH="hate_speech",
            HARM_CATEGORY_SEXUALLY_EXPLICIT="sexually_explicit",
            HARM_CATEGORY_DANGEROUS_CONTENT="dangerous_content",
        ),
        HarmBlockThreshold=SimpleNamespace(BLOCK_ONLY_HIGH="block_only_high"),
        SafetySetting=FakeSafetySetting,
    )

    result = build_safety_config(types_module=fake_types)

    assert len(result) == 4
    assert len(created) == 4


def test_build_safety_config_uses_block_only_high_for_all() -> None:
    created: list[dict] = []

    class FakeSafetySetting:
        def __init__(self, *, category: str, threshold: str) -> None:
            created.append({"category": category, "threshold": threshold})

    fake_types = SimpleNamespace(
        HarmCategory=SimpleNamespace(
            HARM_CATEGORY_HARASSMENT="harassment",
            HARM_CATEGORY_HATE_SPEECH="hate_speech",
            HARM_CATEGORY_SEXUALLY_EXPLICIT="sexually_explicit",
            HARM_CATEGORY_DANGEROUS_CONTENT="dangerous_content",
        ),
        HarmBlockThreshold=SimpleNamespace(BLOCK_ONLY_HIGH="block_only_high"),
        SafetySetting=FakeSafetySetting,
    )

    build_safety_config(types_module=fake_types)

    thresholds = {s["threshold"] for s in created}
    assert thresholds == {"block_only_high"}


def test_build_safety_config_covers_all_four_harm_categories() -> None:
    created: list[dict] = []

    class FakeSafetySetting:
        def __init__(self, *, category: str, threshold: str) -> None:
            created.append({"category": category, "threshold": threshold})

    fake_types = SimpleNamespace(
        HarmCategory=SimpleNamespace(
            HARM_CATEGORY_HARASSMENT="harassment",
            HARM_CATEGORY_HATE_SPEECH="hate_speech",
            HARM_CATEGORY_SEXUALLY_EXPLICIT="sexually_explicit",
            HARM_CATEGORY_DANGEROUS_CONTENT="dangerous_content",
        ),
        HarmBlockThreshold=SimpleNamespace(BLOCK_ONLY_HIGH="block_only_high"),
        SafetySetting=FakeSafetySetting,
    )

    build_safety_config(types_module=fake_types)

    categories = {s["category"] for s in created}
    assert "harassment" in categories
    assert "hate_speech" in categories
    assert "sexually_explicit" in categories
    assert "dangerous_content" in categories


def test_build_safety_config_returns_empty_when_types_missing_safety_setting() -> None:
    fake_types = SimpleNamespace(
        HarmCategory=SimpleNamespace(HARM_CATEGORY_HARASSMENT="harassment"),
        HarmBlockThreshold=SimpleNamespace(BLOCK_ONLY_HIGH="block_only_high"),
        # SafetySetting intentionally absent
    )

    result = build_safety_config(types_module=fake_types)

    assert result == []


# ---------------------------------------------------------------------------
# Epic 4 — build_agent_instruction clinical tool tests
# ---------------------------------------------------------------------------


def test_build_agent_instruction_includes_clinical_alert_tool_name() -> None:
    instruction = build_agent_instruction(native_tools_enabled=True)
    assert "report_clinical_alert" in instruction


def test_build_agent_instruction_clinical_alert_is_silent_from_child() -> None:
    instruction = build_agent_instruction(native_tools_enabled=True)
    assert "NEVER tell the child" in instruction
    assert "NEVER mention the tool" in instruction
    assert "NEVER break character" in instruction


def test_build_agent_instruction_clinical_continues_in_character_after_alert() -> None:
    instruction = build_agent_instruction(native_tools_enabled=True)
    assert "MUST IMMEDIATELY call" in instruction
    assert "VIOLATION" in instruction
    assert "CONTINUE SPEAKING" in instruction


def test_build_agent_instruction_clinical_text_fallback_marker_included() -> None:
    instruction = build_agent_instruction(native_tools_enabled=False)
    assert "report_clinical_alert" in instruction
    # Clinical tool marker format must be present in fallback mode
    assert '"tool":"report_clinical_alert"' in instruction


def test_translate_text_tool_marker_for_clinical_alert() -> None:
    """Text marker for report_clinical_alert must be translated in text_fallback mode."""
    dumped: dict = {
        "content": {
            "parts": [
                {
                    "text": (
                        "[ANIMISM_TOOL_CALL] "
                        '{"tool":"report_clinical_alert","args":{"primary_emotion":"anxiety","trigger":"school","recommended_strategy":"grounding","risk_level":"moderate","child_quote_summary":"scared"}}'
                    )
                }
            ]
        }
    }

    result = AdkGeminiLiveStream._translate_function_calls(dumped)
    assert len(result) == 1
    ev = result[0]
    assert ev["type"] == "tool_call"
    assert ev["tool"] == "report_clinical_alert"
    assert ev["args"]["primary_emotion"] == "anxiety"
    assert ev["args"]["trigger"] == "school"
