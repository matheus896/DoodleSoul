import { describe, expect, it } from "vitest";

import { PcmRingBuffer } from "../pcmRingBuffer";

describe("PcmRingBuffer", () => {
  it("preserves sample order through write/read cycle", () => {
    const ring = new PcmRingBuffer(64);
    ring.write(new Int16Array([100, 200, 300, 400]));

    const out = new Float32Array(4);
    const read = ring.read(out);
    expect(read).toBe(4);
    expect(out[0]).toBeCloseTo(100 / 32768, 4);
    expect(out[1]).toBeCloseTo(200 / 32768, 4);
    expect(out[2]).toBeCloseTo(300 / 32768, 4);
    expect(out[3]).toBeCloseTo(400 / 32768, 4);
  });

  it("returns silence (zeros) on underflow", () => {
    const ring = new PcmRingBuffer(64);
    const out = new Float32Array(128);
    const read = ring.read(out);
    expect(read).toBe(0);
    for (let i = 0; i < out.length; i++) {
      expect(out[i]).toBe(0);
    }
  });

  it("overwrites oldest samples on overflow instead of crashing", () => {
    const ring = new PcmRingBuffer(4);
    ring.write(new Int16Array([1000, 2000, 3000, 4000]));
    ring.write(new Int16Array([5000, 6000]));

    const out = new Float32Array(4);
    const read = ring.read(out);
    expect(read).toBe(4);
    expect(out[0]).toBeCloseTo(3000 / 32768, 4);
    expect(out[1]).toBeCloseTo(4000 / 32768, 4);
    expect(out[2]).toBeCloseTo(5000 / 32768, 4);
    expect(out[3]).toBeCloseTo(6000 / 32768, 4);
  });

  it("handles multiple sequential write/read cycles", () => {
    const ring = new PcmRingBuffer(256);
    ring.write(new Int16Array([100, 200]));
    const out1 = new Float32Array(2);
    ring.read(out1);
    expect(out1[0]).toBeCloseTo(100 / 32768, 4);

    ring.write(new Int16Array([300, 400]));
    const out2 = new Float32Array(2);
    ring.read(out2);
    expect(out2[0]).toBeCloseTo(300 / 32768, 4);
    expect(out2[1]).toBeCloseTo(400 / 32768, 4);
  });

  it("partial read returns only available samples", () => {
    const ring = new PcmRingBuffer(64);
    ring.write(new Int16Array([100, 200]));

    const out = new Float32Array(8);
    const read = ring.read(out);
    expect(read).toBe(2);
    expect(out[0]).toBeCloseTo(100 / 32768, 4);
    expect(out[1]).toBeCloseTo(200 / 32768, 4);
    for (let i = 2; i < 8; i++) {
      expect(out[i]).toBe(0);
    }
  });

  it("flush resets buffer to empty", () => {
    const ring = new PcmRingBuffer(64);
    ring.write(new Int16Array([100, 200, 300]));
    ring.flush();

    const out = new Float32Array(4);
    const read = ring.read(out);
    expect(read).toBe(0);
    expect(ring.bufferedSamples()).toBe(0);
  });

  it("can write immediately after flush (barge-in recovery)", () => {
    const ring = new PcmRingBuffer(64);
    ring.write(new Int16Array([100, 200, 300]));
    ring.flush();
    ring.write(new Int16Array([400, 500]));

    const out = new Float32Array(2);
    const read = ring.read(out);
    expect(read).toBe(2);
    expect(out[0]).toBeCloseTo(400 / 32768, 4);
    expect(out[1]).toBeCloseTo(500 / 32768, 4);
  });

  it("reports accurate buffered sample count", () => {
    const ring = new PcmRingBuffer(256);
    expect(ring.bufferedSamples()).toBe(0);

    ring.write(new Int16Array(100));
    expect(ring.bufferedSamples()).toBe(100);

    const out = new Float32Array(30);
    ring.read(out);
    expect(ring.bufferedSamples()).toBe(70);
  });
});

describe("PcmRingBuffer sustained throughput (soak)", () => {
  it("stays bounded under realistic 24kHz streaming for 60 seconds", () => {
    const sampleRate = 24000;
    const bufferSeconds = 10;
    const ring = new PcmRingBuffer(sampleRate * bufferSeconds);

    const framesPerProcess = 128;
    const processCallsPerSecond = sampleRate / framesPerProcess;
    const totalSeconds = 60;
    const totalProcessCalls = Math.floor(processCallsPerSecond * totalSeconds);

    const chunkSize = 2400;
    const chunksPerSecond = sampleRate / chunkSize;
    const totalChunks = Math.floor(chunksPerSecond * totalSeconds);
    const chunksPerProcessCall = totalChunks / totalProcessCalls;

    let chunkAccumulator = 0;
    let maxBuffered = 0;

    for (let i = 0; i < totalProcessCalls; i++) {
      chunkAccumulator += chunksPerProcessCall;
      while (chunkAccumulator >= 1) {
        ring.write(new Int16Array(chunkSize));
        chunkAccumulator -= 1;
      }

      const out = new Float32Array(framesPerProcess);
      ring.read(out);

      const buffered = ring.bufferedSamples();
      if (buffered > maxBuffered) {
        maxBuffered = buffered;
      }
    }

    expect(maxBuffered).toBeLessThan(sampleRate * bufferSeconds);
    expect(ring.bufferedSamples()).toBeLessThan(sampleRate * 2);
  });

  it("recovers from 500ms burst jitter without unbounded growth", () => {
    const sampleRate = 24000;
    const ring = new PcmRingBuffer(sampleRate * 10);

    const burstSamples = sampleRate / 2;
    ring.write(new Int16Array(burstSamples));
    expect(ring.bufferedSamples()).toBe(burstSamples);

    const framesPerProcess = 128;
    const drainCalls = Math.ceil(burstSamples / framesPerProcess);
    for (let i = 0; i < drainCalls; i++) {
      const out = new Float32Array(framesPerProcess);
      ring.read(out);
    }

    expect(ring.bufferedSamples()).toBeLessThanOrEqual(framesPerProcess);
  });
});
