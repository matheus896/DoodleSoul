import { afterEach, describe, expect, it } from "vitest";

import {
  ACTIVE_SESSION_ID_STORAGE_KEY,
  readActiveSessionId,
  writeActiveSessionId,
} from "../sessionStorage";

describe("sessionStorage", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("writes and reads active session id using canonical key", () => {
    writeActiveSessionId("session-123");
    expect(window.localStorage.getItem(ACTIVE_SESSION_ID_STORAGE_KEY)).toBe("session-123");
    expect(readActiveSessionId()).toBe("session-123");
  });

  it("returns null when storage has no active session id", () => {
    expect(readActiveSessionId()).toBeNull();
  });
});
