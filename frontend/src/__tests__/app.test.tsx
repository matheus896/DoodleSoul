import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const { playerConstructorSpy } = vi.hoisted(() => ({
  playerConstructorSpy: vi.fn(function MockPcm24kPlayer() {
    return {
      enqueue: vi.fn(),
      pullChunk: vi.fn().mockReturnValue(new Int16Array(0)),
      flush: vi.fn(),
      getMetrics: vi.fn().mockReturnValue({
        enqueuedChunks: 0,
        pulledChunks: 0,
        underflowCount: 0,
        overflowDropCount: 0,
        flushCount: 0,
        peakBufferedSamples: 0,
        totalEnqueuedSamples: 0,
        totalPulledSamples: 0,
      }),
    };
  }),
}));

vi.mock("../audio/pcmPlayer", () => ({
  Pcm24kPlayer: playerConstructorSpy,
}));

import App from "../App";

describe("App player wiring", () => {
  it("configures player catchup threshold to 1 second", () => {
    renderToString(<App />);
    expect(playerConstructorSpy).toHaveBeenCalledWith(24000 * 2, 24000);
  });
});
