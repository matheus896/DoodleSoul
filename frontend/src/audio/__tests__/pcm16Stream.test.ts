import { describe, expect, it } from "vitest";

import { decodePcm16StreamChunk } from "../pcm16Stream";

describe("decodePcm16StreamChunk", () => {
  it("decodes even-length little-endian PCM16 payload", () => {
    const bytes = new Uint8Array([0x01, 0x00, 0xff, 0xff]); // 1, -1
    const { samples, carry } = decodePcm16StreamChunk(bytes.buffer);

    expect(Array.from(samples)).toEqual([1, -1]);
    expect(carry.length).toBe(0);
  });

  it("keeps trailing odd byte as carry and completes on next chunk", () => {
    const first = new Uint8Array([0x34]); // low byte only
    const firstDecoded = decodePcm16StreamChunk(first.buffer);
    expect(firstDecoded.samples.length).toBe(0);
    expect(Array.from(firstDecoded.carry)).toEqual([0x34]);

    const second = new Uint8Array([0x12, 0x78, 0x56]); // completes 0x1234 and 0x5678
    const secondDecoded = decodePcm16StreamChunk(second.buffer, firstDecoded.carry);
    expect(Array.from(secondDecoded.samples)).toEqual([0x1234, 0x5678]);
    expect(secondDecoded.carry.length).toBe(0);
  });

  it("returns empty samples for empty chunk", () => {
    const { samples, carry } = decodePcm16StreamChunk(new ArrayBuffer(0));
    expect(samples.length).toBe(0);
    expect(carry.length).toBe(0);
  });
});
