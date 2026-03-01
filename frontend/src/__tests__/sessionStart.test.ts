import { describe, expect, it } from "vitest";

import {
  buildLiveWebSocketUrl,
  validateConsentForStart,
} from "../session/startSession";

describe("validateConsentForStart", () => {
  it("returns ok for explicit consent", () => {
    const result = validateConsentForStart(true);
    expect(result.ok).toBe(true);
  });

  it("returns actionable error for missing consent", () => {
    const result = validateConsentForStart(false);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.message).toContain("consentimento");
    }
  });
});

describe("buildLiveWebSocketUrl", () => {
  it("builds websocket URL from API origin and session id", () => {
    const url = buildLiveWebSocketUrl({
      sessionId: "abc-123",
      apiBaseUrl: "https://animism.example.com",
    });

    expect(url).toBe("wss://animism.example.com/ws/live/abc-123");
  });

  it("replaces session placeholder in template", () => {
    const url = buildLiveWebSocketUrl({
      sessionId: "session-x",
      wsUrlTemplate: "wss://animism.example.com/ws/live/{session_id}",
    });

    expect(url).toBe("wss://animism.example.com/ws/live/session-x");
  });

  it("replaces trailing session segment when template has fixed ws path", () => {
    const url = buildLiveWebSocketUrl({
      sessionId: "session-new",
      wsUrlTemplate: "ws://mock.local/ws/live/test",
    });

    expect(url).toBe("ws://mock.local/ws/live/session-new");
  });
});
