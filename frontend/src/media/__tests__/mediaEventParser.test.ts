/**
 * Tests for mediaEventParser — validates type narrowing and rejection
 * of malformed payloads.
 *
 * @see validation-frontend-epic3-story.md — F3.1 AC1
 */

import { describe, expect, it } from "vitest";

import { parseMediaEvent, classifyMediaPayload, DROP_REASON } from "../mediaEventParser";

describe("parseMediaEvent", () => {
  // ── Positive cases ──

  it("parses drawing_in_progress (system_instruction)", () => {
    const input = {
      type: "system_instruction",
      text: "drawing_in_progress",
      scene_id: "scene-1",
    };
    const result = parseMediaEvent(input);
    expect(result).not.toBeNull();
    expect(result!.type).toBe("system_instruction");
    expect(result!.scene_id).toBe("scene-1");
  });

  it("parses media.image.created", () => {
    const input = {
      type: "media.image.created",
      scene_id: "scene-1",
      media_type: "image",
      url: "mock://imagen/scene-1.png",
      width: 1024,
      height: 1024,
      payload_size_bytes: 51200,
      _mock_payload: "x".repeat(100),
    };
    const result = parseMediaEvent(input);
    expect(result).not.toBeNull();
    expect(result!.type).toBe("media.image.created");
    if (result!.type === "media.image.created") {
      expect(result.url).toBe("mock://imagen/scene-1.png");
      expect(result.width).toBe(1024);
      expect(result.height).toBe(1024);
    }
  });

  it("parses media_delayed", () => {
    const input = {
      type: "media_delayed",
      scene_id: "scene-2",
      elapsed_seconds: 30,
    };
    const result = parseMediaEvent(input);
    expect(result).not.toBeNull();
    expect(result!.type).toBe("media_delayed");
    if (result!.type === "media_delayed") {
      expect(result.elapsed_seconds).toBe(30);
    }
  });

  it("parses media.video.created", () => {
    const input = {
      type: "media.video.created",
      scene_id: "scene-2",
      media_type: "video",
      url: "mock://veo/scene-2.mp4",
      duration_seconds: 8,
      payload_size_bytes: 102400,
      _mock_payload: "x".repeat(200),
    };
    const result = parseMediaEvent(input);
    expect(result).not.toBeNull();
    expect(result!.type).toBe("media.video.created");
    if (result!.type === "media.video.created") {
      expect(result.url).toBe("mock://veo/scene-2.mp4");
      expect(result.duration_seconds).toBe(8);
    }
  });

  // ── Negative cases (must return null) ──

  it("returns null for null/undefined", () => {
    expect(parseMediaEvent(null)).toBeNull();
    expect(parseMediaEvent(undefined)).toBeNull();
  });

  it("returns null for non-object", () => {
    expect(parseMediaEvent("string")).toBeNull();
    expect(parseMediaEvent(42)).toBeNull();
    expect(parseMediaEvent(true)).toBeNull();
  });

  it("returns null for unknown type", () => {
    expect(parseMediaEvent({ type: "unknown", scene_id: "s" })).toBeNull();
  });

  it("returns null for missing scene_id", () => {
    expect(
      parseMediaEvent({ type: "system_instruction", text: "drawing_in_progress" }),
    ).toBeNull();
  });

  it("returns null for empty scene_id", () => {
    expect(
      parseMediaEvent({
        type: "system_instruction",
        text: "drawing_in_progress",
        scene_id: "",
      }),
    ).toBeNull();
  });

  it("returns null for system_instruction with wrong text", () => {
    expect(
      parseMediaEvent({
        type: "system_instruction",
        text: "some_other_instruction",
        scene_id: "s",
      }),
    ).toBeNull();
  });

  it("returns null for media.image.created missing url", () => {
    expect(
      parseMediaEvent({
        type: "media.image.created",
        scene_id: "s",
        width: 1024,
        height: 1024,
      }),
    ).toBeNull();
  });

  it("returns null for media.image.created missing dimensions", () => {
    expect(
      parseMediaEvent({
        type: "media.image.created",
        scene_id: "s",
        url: "mock://test",
      }),
    ).toBeNull();
  });

  it("returns null for media_delayed missing elapsed_seconds", () => {
    expect(
      parseMediaEvent({ type: "media_delayed", scene_id: "s" }),
    ).toBeNull();
  });

  it("returns null for media.video.created missing url", () => {
    expect(
      parseMediaEvent({
        type: "media.video.created",
        scene_id: "s",
        duration_seconds: 8,
      }),
    ).toBeNull();
  });

  it("returns null for media.video.created missing duration", () => {
    expect(
      parseMediaEvent({
        type: "media.video.created",
        scene_id: "s",
        url: "mock://test",
      }),
    ).toBeNull();
  });

  // ── Edge: ADK audio events should not match ──

  it("returns null for ADK audio events (no type field)", () => {
    const adkEvent = {
      content: {
        parts: [
          {
            inlineData: {
              mimeType: "audio/pcm;rate=24000",
              data: "AQID",
            },
          },
        ],
      },
    };
    expect(parseMediaEvent(adkEvent)).toBeNull();
  });

  it("returns null for text-only events", () => {
    expect(parseMediaEvent({ text: "Hello!" })).toBeNull();
  });

  it("returns null for type=text narrative events", () => {
    expect(
      parseMediaEvent({ type: "text", text: "I'm drawing your robot!" }),
    ).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// classifyMediaPayload — drop reason diagnostics (Epic 3 Observability)
// ---------------------------------------------------------------------------

describe("classifyMediaPayload — drop reasons", () => {
  it("returns NOT_AN_OBJECT for null", () => {
    expect(classifyMediaPayload(null).dropReason).toBe(DROP_REASON.NOT_AN_OBJECT);
  });

  it("returns NOT_AN_OBJECT for string", () => {
    expect(classifyMediaPayload("hello").dropReason).toBe(DROP_REASON.NOT_AN_OBJECT);
  });

  it("returns NOT_AN_OBJECT for number", () => {
    expect(classifyMediaPayload(42).dropReason).toBe(DROP_REASON.NOT_AN_OBJECT);
  });

  it("returns NO_TYPE_FIELD for object without type", () => {
    expect(classifyMediaPayload({ scene_id: "s" }).dropReason).toBe(DROP_REASON.NO_TYPE_FIELD);
  });

  it("returns UNKNOWN_EVENT_TYPE for unrecognised type", () => {
    expect(
      classifyMediaPayload({ type: "unknown_thing", scene_id: "s" }).dropReason,
    ).toBe(DROP_REASON.UNKNOWN_EVENT_TYPE);
  });

  it("returns UNKNOWN_EVENT_TYPE for type=text", () => {
    expect(
      classifyMediaPayload({ type: "text", text: "hi" }).dropReason,
    ).toBe(DROP_REASON.UNKNOWN_EVENT_TYPE);
  });

  it("returns MISSING_SCENE_ID when scene_id absent on recognised type", () => {
    expect(
      classifyMediaPayload({ type: "system_instruction", text: "drawing_in_progress" }).dropReason,
    ).toBe(DROP_REASON.MISSING_SCENE_ID);
  });

  it("returns MISSING_SCENE_ID for empty string scene_id", () => {
    expect(
      classifyMediaPayload({
        type: "system_instruction",
        text: "drawing_in_progress",
        scene_id: "",
      }).dropReason,
    ).toBe(DROP_REASON.MISSING_SCENE_ID);
  });

  it("returns INSTRUCTION_WRONG_TEXT for system_instruction with unexpected text", () => {
    expect(
      classifyMediaPayload({
        type: "system_instruction",
        text: "some_other_instruction",
        scene_id: "s",
      }).dropReason,
    ).toBe(DROP_REASON.INSTRUCTION_WRONG_TEXT);
  });

  it("returns IMAGE_MISSING_URL for media.image.created without url", () => {
    expect(
      classifyMediaPayload({
        type: "media.image.created",
        scene_id: "s",
        width: 1024,
        height: 1024,
      }).dropReason,
    ).toBe(DROP_REASON.IMAGE_MISSING_URL);
  });

  it("returns IMAGE_MISSING_DIMENSIONS for media.image.created without width/height", () => {
    expect(
      classifyMediaPayload({
        type: "media.image.created",
        scene_id: "s",
        url: "mock://test",
      }).dropReason,
    ).toBe(DROP_REASON.IMAGE_MISSING_DIMENSIONS);
  });

  it("returns DELAYED_MISSING_ELAPSED for media_delayed without elapsed_seconds", () => {
    expect(
      classifyMediaPayload({ type: "media_delayed", scene_id: "s" }).dropReason,
    ).toBe(DROP_REASON.DELAYED_MISSING_ELAPSED);
  });

  it("returns VIDEO_MISSING_URL for media.video.created without url", () => {
    expect(
      classifyMediaPayload({
        type: "media.video.created",
        scene_id: "s",
        duration_seconds: 8,
      }).dropReason,
    ).toBe(DROP_REASON.VIDEO_MISSING_URL);
  });

  it("returns VIDEO_MISSING_DURATION for media.video.created without duration_seconds", () => {
    expect(
      classifyMediaPayload({
        type: "media.video.created",
        scene_id: "s",
        url: "mock://test",
      }).dropReason,
    ).toBe(DROP_REASON.VIDEO_MISSING_DURATION);
  });

  // ── Success cases return null dropReason ──

  it("returns null dropReason for valid system_instruction", () => {
    const { event, dropReason } = classifyMediaPayload({
      type: "system_instruction",
      text: "drawing_in_progress",
      scene_id: "s",
    });
    expect(dropReason).toBeNull();
    expect(event).not.toBeNull();
  });

  it("parses drawing_in_progress (direct orchestrator format) and normalises to system_instruction", () => {
    const { event, dropReason } = classifyMediaPayload({
      type: "drawing_in_progress",
      scene_id: "scene-orch",
    });
    expect(dropReason).toBeNull();
    expect(event).not.toBeNull();
    expect(event!.type).toBe("system_instruction");
    expect(event!.scene_id).toBe("scene-orch");
  });

  it("returns null dropReason for valid media.image.created", () => {
    const { event, dropReason } = classifyMediaPayload({
      type: "media.image.created",
      scene_id: "s",
      url: "mock://img",
      width: 1024,
      height: 1024,
    });
    expect(dropReason).toBeNull();
    expect(event).not.toBeNull();
  });

  it("returns null dropReason for valid media_delayed", () => {
    const { dropReason } = classifyMediaPayload({
      type: "media_delayed",
      scene_id: "s",
      elapsed_seconds: 30,
    });
    expect(dropReason).toBeNull();
  });

  it("returns null dropReason for valid media.video.created", () => {
    const { dropReason } = classifyMediaPayload({
      type: "media.video.created",
      scene_id: "s",
      url: "mock://vid",
      duration_seconds: 8,
    });
    expect(dropReason).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// parseMediaEvent — drawing_in_progress compat (new in Epic 3 Observability)
// ---------------------------------------------------------------------------

describe("parseMediaEvent — drawing_in_progress compat", () => {
  it("accepts direct drawing_in_progress format (MediaOrchestrator output)", () => {
    const result = parseMediaEvent({
      type: "drawing_in_progress",
      scene_id: "scene-1",
    });
    expect(result).not.toBeNull();
    expect(result!.type).toBe("system_instruction");
    expect(result!.scene_id).toBe("scene-1");
  });

  it("still accepts legacy system_instruction format (pilot mock)", () => {
    const result = parseMediaEvent({
      type: "system_instruction",
      text: "drawing_in_progress",
      scene_id: "scene-2",
    });
    expect(result).not.toBeNull();
    expect(result!.type).toBe("system_instruction");
  });
});
