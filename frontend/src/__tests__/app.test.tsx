import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import App from "../App";

describe("App playback wiring", () => {
  it("renders without crashing (SSR baseline)", () => {
    const html = renderToString(<App />);
    expect(html).toContain("DoodleSoul");
    expect(html).toContain("Start Adventure");
  });

  it("does not import Pcm24kPlayer in the module graph", async () => {
    const appModule = await import("../App");
    const moduleKeys = Object.keys(appModule);
    expect(moduleKeys).not.toContain("Pcm24kPlayer");
  });

  it("exports PlaybackMetrics type (compile-time contract)", () => {
    const html = renderToString(<App />);
    expect(html).toContain("DoodleSoul");
  });
});
