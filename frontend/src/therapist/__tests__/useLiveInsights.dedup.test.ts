/**
 * Unit tests for dedupeAlerts — the idempotent alert-deduplication guard.
 *
 * Root cause context (finalday1.md / finaldaylessons.md):
 * - Backend `add_alert()` is additive (plain append, no dedup).
 * - LLM can fire `report_clinical_alert` multiple times for the same emotional
 *   state before the prompt debounce fully settles.
 * - React 18 Strict Mode runs useEffect twice in development, which can trigger
 *   two simultaneous initial fetches feeding the same payload into state.
 * - Fix: deduplicate by content fingerprint at the frontend boundary (idempotent update).
 */

import { describe, expect, it } from "vitest";
import { dedupeAlerts, type ClinicalAlert } from "../useLiveInsights";

const ALERT_A: ClinicalAlert = {
  primary_emotion: "anxious",
  trigger: "mention of school",
  risk_level: "medium",
  recommended_strategy: "grounding exercise",
  child_quote_summary: "I don't like going to school",
};

const ALERT_B: ClinicalAlert = {
  primary_emotion: "happy",
  trigger: "",
  risk_level: "none",
  recommended_strategy: "",
  child_quote_summary: "I love drawing!",
};

const ALERT_A_VARIANT: ClinicalAlert = {
  ...ALERT_A,
  trigger: "mention of homework", // different trigger → legitimately different alert
};

describe("dedupeAlerts", () => {
  it("returns empty array for empty input", () => {
    expect(dedupeAlerts([])).toEqual([]);
  });

  it("returns the same single alert unchanged", () => {
    expect(dedupeAlerts([ALERT_A])).toEqual([ALERT_A]);
  });

  it("removes exact duplicate alert — idempotent on same payload twice", () => {
    const input = [ALERT_A, ALERT_A];
    const result = dedupeAlerts(input);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual(ALERT_A);
  });

  it("removes duplicate even when interspersed with other alerts", () => {
    const input = [ALERT_A, ALERT_B, ALERT_A];
    const result = dedupeAlerts(input);
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual(ALERT_A);
    expect(result[1]).toEqual(ALERT_B);
  });

  it("preserves first occurrence — subsequent duplicates are dropped", () => {
    const alertFirst = { ...ALERT_A };
    const alertSecond = { ...ALERT_A }; // identical content, different reference
    const result = dedupeAlerts([alertFirst, alertSecond]);
    expect(result).toHaveLength(1);
    expect(result[0]).toBe(alertFirst); // first occurrence reference preserved
  });

  it("keeps alerts that differ only in one field (not false-duplicates)", () => {
    const input = [ALERT_A, ALERT_A_VARIANT];
    const result = dedupeAlerts(input);
    expect(result).toHaveLength(2);
  });

  it("keeps all alerts when no duplicates exist", () => {
    const input = [ALERT_A, ALERT_B, ALERT_A_VARIANT];
    const result = dedupeAlerts(input);
    expect(result).toHaveLength(3);
  });

  it("handles multiple identical duplicates — only one survives", () => {
    const input = [ALERT_A, ALERT_A, ALERT_A, ALERT_B, ALERT_B];
    const result = dedupeAlerts(input);
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual(ALERT_A);
    expect(result[1]).toEqual(ALERT_B);
  });

  it("does not mutate the input array", () => {
    const input = [ALERT_A, ALERT_A];
    const inputCopy = [...input];
    dedupeAlerts(input);
    expect(input).toEqual(inputCopy);
  });
});
