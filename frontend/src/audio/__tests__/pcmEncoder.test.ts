import { describe, expect, it } from "vitest";

import { downsampleTo16kPcm16, encodePcm16Chunk } from "../pcmEncoder";


describe("downsampleTo16kPcm16", () => {
  it("converts 48kHz input into ~1/3 sample count at 16kHz", () => {
    const input = new Float32Array(480);
    const output = downsampleTo16kPcm16(input, 48000);

    expect(output.length).toBe(160);
  });

  it("converts 44.1kHz input into deterministic 16kHz sample count", () => {
    const input = new Float32Array(441);
    const output = downsampleTo16kPcm16(input, 44100);

    expect(output.length).toBe(160);
  });

  it("clips values to int16 range", () => {
    const input = new Float32Array([2, -2, 0.5, -0.5]);
    const output = downsampleTo16kPcm16(input, 16000);

    expect(output[0]).toBe(32767);
    expect(output[1]).toBe(-32768);
  });

  it("encodes framed chunk as array buffer for websocket transmission", () => {
    const input = new Float32Array(480);
    const payload = encodePcm16Chunk(input, 48000);

    const pcm = new Int16Array(payload);
    expect(pcm.length).toBe(160);
  });
});
