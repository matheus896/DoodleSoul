import { describe, expect, it, vi } from "vitest";

import {
  derivePersonaFromDrawing,
  type PersonaDerivationResult,
} from "../session/personaDerivation";

describe("derivePersonaFromDrawing", () => {
  it("returns drawing-derived persona payload on success", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        status: "ok",
        data: {
          session_id: "session-123",
          persona_source: "drawing_derived",
          fallback_applied: false,
          voice_traits: ["warm", "playful"],
          personality_traits: ["curious", "kind"],
          greeting_text: "Oi Luna, sou seu amigo do desenho!",
        },
      }),
    }));

    const result = await derivePersonaFromDrawing({
      sessionId: "session-123",
      drawingImageBase64: "aGVsbG8=",
      drawingMimeType: "image/png",
      childContext: { childName: "Luna" },
      fetchImpl: fetchMock,
      apiBaseUrl: "https://animism.example.com",
    });

    const typedResult = result as PersonaDerivationResult;
    expect(typedResult.sessionId).toBe("session-123");
    expect(typedResult.personaSource).toBe("drawing_derived");
    expect(typedResult.fallbackApplied).toBe(false);
    expect(typedResult.voiceTraits.length).toBeGreaterThan(0);
    expect(typedResult.personalityTraits.length).toBeGreaterThan(0);
    expect(typedResult.greetingText).toContain("Luna");
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("returns fallback persona payload when derivation times out", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        status: "ok",
        data: {
          session_id: "session-123",
          persona_source: "fallback",
          fallback_applied: true,
          fallback_reason: "derivation_timeout",
          voice_traits: ["gentle"],
          personality_traits: ["calm"],
          greeting_text: "Oi, vamos brincar juntos!",
        },
      }),
    }));

    const result = await derivePersonaFromDrawing({
      sessionId: "session-123",
      drawingImageBase64: "aGVsbG8=",
      drawingMimeType: "image/png",
      fetchImpl: fetchMock,
      apiBaseUrl: "https://animism.example.com",
    });

    expect(result.personaSource).toBe("fallback");
    expect(result.fallbackApplied).toBe(true);
    expect(result.fallbackReason).toBe("derivation_timeout");
    expect(result.greetingText.length).toBeGreaterThan(0);
  });
});
