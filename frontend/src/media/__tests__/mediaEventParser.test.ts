/**
 * Tests for mediaEventParser — validates type narrowing and rejection
 * of malformed payloads.
 *
 * @see validation-frontend-epic3-story.md — F3.1 AC1
 */

import { describe, expect, it } from "vitest";

import { parseMediaEvent } from "../mediaEventParser";

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
