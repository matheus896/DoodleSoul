import { afterEach, describe, expect, it } from "vitest";

import { ACTIVE_SESSION_ID_STORAGE_KEY } from "../../session/sessionStorage";
import { resolveLiveInsightsSessionId } from "../LiveInsightsPage";

describe("resolveLiveInsightsSessionId", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("prioritizes query param over localStorage", () => {
    window.localStorage.setItem(ACTIVE_SESSION_ID_STORAGE_KEY, "session-storage");
    const params = new URLSearchParams("session_id=session-query");

    expect(resolveLiveInsightsSessionId(params)).toBe("session-query");
  });

  it("falls back to localStorage when query param is absent", () => {
    window.localStorage.setItem(ACTIVE_SESSION_ID_STORAGE_KEY, "session-storage");
    const params = new URLSearchParams();

    expect(resolveLiveInsightsSessionId(params)).toBe("session-storage");
  });

  it("returns null when both query param and localStorage are absent", () => {
    const params = new URLSearchParams();
    expect(resolveLiveInsightsSessionId(params)).toBeNull();
  });
});
