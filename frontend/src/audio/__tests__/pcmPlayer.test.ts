import { describe, expect, it } from "vitest";

import { Pcm24kPlayer } from "../pcmPlayer";
import type { PlayerMetrics } from "../pcmPlayer";


describe("Pcm24kPlayer", () => {
  it("preserves enqueue/dequeue order for 24kHz chunks", () => {
    const player = new Pcm24kPlayer(32);
    player.enqueue(new Int16Array([1, 2, 3]));
    player.enqueue(new Int16Array([4, 5]));

    const pulled = player.pullChunk(5);
    expect(Array.from(pulled)).toEqual([1, 2, 3, 4, 5]);
  });

  it("bounds buffer and drops stale audio to avoid accumulated latency", () => {
    const player = new Pcm24kPlayer(4);
    player.enqueue(new Int16Array([1, 2, 3]));
    player.enqueue(new Int16Array([4, 5, 6]));

    expect(player.getBufferedSampleCount()).toBeLessThanOrEqual(4);
    expect(Array.from(player.pullChunk(10))).toEqual([4, 5, 6]);
  });

  it("flushes buffered audio and handles underflow", () => {
    const player = new Pcm24kPlayer();

    player.enqueue(new Int16Array([1, 2, 3]));
    player.flush();

    expect(player.getBufferedSampleCount()).toBe(0);
    expect(player.pullChunk(8).length).toBe(0);
  });
});


describe("Pcm24kPlayer metrics", () => {
  it("exposes metrics snapshot with correct types", () => {
    const player = new Pcm24kPlayer();
    const metrics: PlayerMetrics = player.getMetrics();

    expect(metrics).toHaveProperty("enqueuedChunks");
    expect(metrics).toHaveProperty("pulledChunks");
    expect(metrics).toHaveProperty("underflowCount");
    expect(metrics).toHaveProperty("overflowDropCount");
    expect(metrics).toHaveProperty("flushCount");
    expect(metrics).toHaveProperty("peakBufferedSamples");
    expect(metrics).toHaveProperty("totalEnqueuedSamples");
    expect(metrics).toHaveProperty("totalPulledSamples");
  });

  it("tracks enqueue and pull counts accurately", () => {
    const player = new Pcm24kPlayer(1000);
    player.enqueue(new Int16Array([1, 2, 3]));
    player.enqueue(new Int16Array([4, 5]));
    player.pullChunk(3);

    const metrics = player.getMetrics();
    expect(metrics.enqueuedChunks).toBe(2);
    expect(metrics.pulledChunks).toBe(1);
    expect(metrics.totalEnqueuedSamples).toBe(5);
    expect(metrics.totalPulledSamples).toBe(3);
  });

  it("counts underflow events when pullChunk finds empty buffer", () => {
    const player = new Pcm24kPlayer();
    player.pullChunk(128);
    player.pullChunk(128);

    const metrics = player.getMetrics();
    expect(metrics.underflowCount).toBe(2);
  });

  it("counts overflow drops when enqueue exceeds max buffer", () => {
    const player = new Pcm24kPlayer(4);
    player.enqueue(new Int16Array([1, 2, 3]));
    player.enqueue(new Int16Array([4, 5, 6]));

    const metrics = player.getMetrics();
    expect(metrics.overflowDropCount).toBeGreaterThanOrEqual(1);
  });

  it("tracks flush events", () => {
    const player = new Pcm24kPlayer();
    player.enqueue(new Int16Array([1, 2, 3]));
    player.flush();
    player.enqueue(new Int16Array([4, 5]));
    player.flush();

    const metrics = player.getMetrics();
    expect(metrics.flushCount).toBe(2);
  });

  it("records peak buffered sample count", () => {
    const player = new Pcm24kPlayer(1000);
    player.enqueue(new Int16Array(100));
    player.enqueue(new Int16Array(200));

    const metrics = player.getMetrics();
    expect(metrics.peakBufferedSamples).toBe(300);

    player.pullChunk(300);
    expect(player.getMetrics().peakBufferedSamples).toBe(300);
  });

  it("resets metrics to zero via resetMetrics()", () => {
    const player = new Pcm24kPlayer();
    player.enqueue(new Int16Array([1, 2]));
    player.pullChunk(10);
    player.flush();
    player.resetMetrics();

    const metrics = player.getMetrics();
    expect(metrics.enqueuedChunks).toBe(0);
    expect(metrics.pulledChunks).toBe(0);
    expect(metrics.underflowCount).toBe(0);
    expect(metrics.overflowDropCount).toBe(0);
    expect(metrics.flushCount).toBe(0);
    expect(metrics.peakBufferedSamples).toBe(0);
    expect(metrics.totalEnqueuedSamples).toBe(0);
    expect(metrics.totalPulledSamples).toBe(0);
  });
});


describe("Pcm24kPlayer drift-bounded catchup", () => {
  it("trims excess buffer when drift exceeds catchup threshold", () => {
    const maxBuf = 24000;
    const catchupThreshold = 12000;
    const player = new Pcm24kPlayer(maxBuf, catchupThreshold);

    player.enqueue(new Int16Array(15000));

    expect(player.getBufferedSampleCount()).toBeLessThanOrEqual(catchupThreshold);
    expect(player.getMetrics().overflowDropCount).toBeGreaterThanOrEqual(1);
  });

  it("does not trim when buffer is within catchup threshold", () => {
    const player = new Pcm24kPlayer(24000, 12000);

    player.enqueue(new Int16Array(5000));

    expect(player.getBufferedSampleCount()).toBe(5000);
    expect(player.getMetrics().overflowDropCount).toBe(0);
  });

  it("maintains stability under sustained jitter pattern (soak simulation)", () => {
    const sampleRate = 24000;
    const maxBuffer = sampleRate * 2;
    const catchupThreshold = sampleRate;
    const player = new Pcm24kPlayer(maxBuffer, catchupThreshold);

    const chunkSize = 480;
    const pullInterval = 480;
    const totalIterations = 15000;

    let maxObservedBuffer = 0;

    for (let i = 0; i < totalIterations; i++) {
      const jitterSamples = Math.random() < 0.05 ? chunkSize * 3 : chunkSize;
      player.enqueue(new Int16Array(jitterSamples));

      if (i % 1 === 0) {
        player.pullChunk(pullInterval);
      }

      const buffered = player.getBufferedSampleCount();
      if (buffered > maxObservedBuffer) {
        maxObservedBuffer = buffered;
      }
    }

    expect(maxObservedBuffer).toBeLessThanOrEqual(maxBuffer);

    const metrics = player.getMetrics();
    expect(metrics.enqueuedChunks).toBe(totalIterations);
    expect(metrics.pulledChunks).toBe(totalIterations);
    expect(metrics.peakBufferedSamples).toBeLessThanOrEqual(maxBuffer);
  });

  it("recovers from burst jitter without unbounded growth", () => {
    const player = new Pcm24kPlayer(24000, 12000);

    for (let i = 0; i < 50; i++) {
      player.enqueue(new Int16Array(2400));
    }

    expect(player.getBufferedSampleCount()).toBeLessThanOrEqual(12000);

    player.pullChunk(12000);
    player.enqueue(new Int16Array(480));
    expect(player.getBufferedSampleCount()).toBe(480);
  });
});


describe("Pcm24kPlayer interruption flush policy", () => {
  it("flush during active playback resets completely", () => {
    const player = new Pcm24kPlayer(24000, 12000);

    player.enqueue(new Int16Array(5000));
    player.enqueue(new Int16Array(3000));
    player.flush();

    expect(player.getBufferedSampleCount()).toBe(0);
    expect(player.pullChunk(1000).length).toBe(0);
    expect(player.getMetrics().flushCount).toBe(1);
  });

  it("can enqueue immediately after flush (barge-in recovery)", () => {
    const player = new Pcm24kPlayer(24000, 12000);

    player.enqueue(new Int16Array(10000));
    player.flush();
    player.enqueue(new Int16Array([10, 20, 30]));

    expect(player.getBufferedSampleCount()).toBe(3);
    const pulled = player.pullChunk(3);
    expect(Array.from(pulled)).toEqual([10, 20, 30]);
  });

  it("multiple rapid flushes are safe", () => {
    const player = new Pcm24kPlayer(24000, 12000);

    for (let i = 0; i < 100; i++) {
      player.enqueue(new Int16Array(480));
      player.flush();
    }

    expect(player.getBufferedSampleCount()).toBe(0);
    expect(player.getMetrics().flushCount).toBe(100);
  });
});
