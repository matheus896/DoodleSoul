import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import DemoPage from "../DemoPage";

describe("DemoPage", () => {
  it("renders two same-origin iframes for session and therapist live", () => {
    const html = renderToString(<DemoPage />);

    expect(html).toContain('src="/session"');
    expect(html).toContain('src="/therapist/live"');
  });

  it("grants microphone permission to the child iframe", () => {
    const html = renderToString(<DemoPage />);
    expect(html).toContain('allow="microphone"');
  });
});
