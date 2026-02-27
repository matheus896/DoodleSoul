import { describe, expect, it } from "vitest";

import { Pcm24kPlayer } from "../pcmPlayer";


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
