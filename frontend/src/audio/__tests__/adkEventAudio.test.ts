import { describe, expect, it } from "vitest";

import { extractPcmAudioChunksFromAdkEvent } from "../adkEventAudio";

describe("extractPcmAudioChunksFromAdkEvent", () => {
  it("extracts camelCase inlineData audio chunk and sample rate", () => {
    const payload = {
      content: {
        parts: [
          {
            inlineData: {
              mimeType: "audio/pcm;rate=24000",
              data: "AQACAAMA",
            },
          },
        ],
      },
    };

    const chunks = extractPcmAudioChunksFromAdkEvent(payload);
    expect(chunks).toHaveLength(1);
    expect(chunks[0]?.sampleRate).toBe(24000);
    expect(new Uint8Array(chunks[0]?.buffer ?? new ArrayBuffer(0)).length).toBe(6);
  });

  it("extracts snake_case inline_data audio chunk and sample rate", () => {
    const payload = {
      content: {
        parts: [
          {
            inline_data: {
              mime_type: "audio/pcm;rate=16000",
              data: "AQACAAMA",
            },
          },
        ],
      },
    };

    const chunks = extractPcmAudioChunksFromAdkEvent(payload);
    expect(chunks).toHaveLength(1);
    expect(chunks[0]?.sampleRate).toBe(16000);
  });

  it("ignores non-audio parts", () => {
    const payload = {
      content: {
        parts: [
          {
            text: "hello",
          },
          {
            inlineData: {
              mimeType: "image/jpeg",
              data: "AAAA",
            },
          },
        ],
      },
    };

    const chunks = extractPcmAudioChunksFromAdkEvent(payload);
    expect(chunks).toHaveLength(0);
  });
});
