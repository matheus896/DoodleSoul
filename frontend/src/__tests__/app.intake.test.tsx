import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  requestSessionStartMock,
  buildLiveWebSocketUrlMock,
  validateConsentForStartMock,
  derivePersonaFromDrawingMock,
} = vi.hoisted(() => ({
  requestSessionStartMock: vi.fn<() => Promise<string>>(),
  buildLiveWebSocketUrlMock: vi.fn<() => string>(),
  validateConsentForStartMock: vi.fn<
    (caregiverConsent: boolean) => { ok: boolean; message?: string }
  >(),
  derivePersonaFromDrawingMock: vi.fn<() => Promise<{ greetingText: string }>>(),
}));

vi.mock("../session/startSession", () => ({
  requestSessionStart: requestSessionStartMock,
  buildLiveWebSocketUrl: buildLiveWebSocketUrlMock,
  validateConsentForStart: validateConsentForStartMock,
}));

vi.mock("../session/personaDerivation", () => ({
  derivePersonaFromDrawing: derivePersonaFromDrawingMock,
}));

import App from "../App";

class FakeAudioContext {
  audioWorklet = {
    addModule: vi.fn(async () => {}),
  };

  destination = {};
  resume = vi.fn(async () => {});
  close = vi.fn(async () => {});
  createMediaStreamSource = vi.fn(() => ({
    connect: vi.fn(),
  }));
}

class FakeAudioWorkletNode {
  port = {
    postMessage: vi.fn(),
    onmessage: null as ((event: MessageEvent) => void) | null,
  };

  connect = vi.fn();
}

class FakeWebSocket {
  static OPEN = 1;

  binaryType = "blob";
  readyState = FakeWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();

  constructor(public url: string) {}
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function flushPromises() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function renderApp() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<App />);
  });

  return { container, root };
}

function getStartButton(container: HTMLElement): HTMLButtonElement {
  const buttons = Array.from(container.querySelectorAll("button"));
  const btn = buttons.find(b => b.textContent?.includes("Start") || b.textContent?.includes("Retry"));
  if (!btn) {
    throw new Error("Start button not found");
  }
  return btn as HTMLButtonElement;
}

function getConsentCheckbox(container: HTMLElement): HTMLInputElement {
  const checkbox = container.querySelector("input[type=\"checkbox\"]");
  if (!(checkbox instanceof HTMLInputElement)) {
    throw new Error("Consent checkbox not found");
  }
  return checkbox;
}

function getDrawingInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]');
  if (!(input instanceof HTMLInputElement)) {
    throw new Error("Drawing input not found");
  }
  return input;
}

async function setCheckboxValue(checkbox: HTMLInputElement, checked: boolean) {
  await act(async () => {
    if (checkbox.checked !== checked) {
      checkbox.click();
    }
  });
}

async function clickButton(button: HTMLButtonElement) {
  await act(async () => {
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}

async function selectDrawing(input: HTMLInputElement, file: File) {
  Object.defineProperty(input, "files", {
    configurable: true,
    value: [file],
  });

  await act(async () => {
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function createDrawingFile() {
  const bytes = new TextEncoder().encode("hello");
  const file = new File([bytes], "drawing.png", { type: "image/png" });
  Object.defineProperty(file, "arrayBuffer", {
    configurable: true,
    value: async () => bytes.buffer.slice(0),
  });
  return file;
}

let originalAudioContext: typeof globalThis.AudioContext | undefined;
let originalAudioWorkletNode: typeof globalThis.AudioWorkletNode | undefined;
let originalWebSocket: typeof globalThis.WebSocket | undefined;
let originalGetUserMedia: typeof navigator.mediaDevices.getUserMedia | undefined;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  document.body.innerHTML = "";
  requestSessionStartMock.mockReset();
  buildLiveWebSocketUrlMock.mockReset();
  validateConsentForStartMock.mockReset();
  derivePersonaFromDrawingMock.mockReset();

  requestSessionStartMock.mockResolvedValue("session-123");
  buildLiveWebSocketUrlMock.mockReturnValue("ws://example.test/ws/live/session-123");
  validateConsentForStartMock.mockImplementation((caregiverConsent: boolean) => {
    if (!caregiverConsent) {
      return { ok: false, message: "Please confirm consent before starting the session." };
    }
    return { ok: true };
  });
  derivePersonaFromDrawingMock.mockResolvedValue({ greetingText: "Hi, Luna!" });

  originalAudioContext = globalThis.AudioContext;
  originalAudioWorkletNode = globalThis.AudioWorkletNode;
  originalWebSocket = globalThis.WebSocket;
  originalGetUserMedia = navigator.mediaDevices?.getUserMedia;

  Object.defineProperty(globalThis, "AudioContext", {
    configurable: true,
    value: FakeAudioContext,
  });
  Object.defineProperty(globalThis, "AudioWorkletNode", {
    configurable: true,
    value: FakeAudioWorkletNode,
  });
  Object.defineProperty(globalThis, "WebSocket", {
    configurable: true,
    value: FakeWebSocket,
  });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn(async () => ({ getTracks: () => [] })),
    },
  });
});

afterEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = false;
  Object.defineProperty(globalThis, "AudioContext", {
    configurable: true,
    value: originalAudioContext,
  });
  Object.defineProperty(globalThis, "AudioWorkletNode", {
    configurable: true,
    value: originalAudioWorkletNode,
  });
  Object.defineProperty(globalThis, "WebSocket", {
    configurable: true,
    value: originalWebSocket,
  });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: originalGetUserMedia,
    },
  });

  await act(async () => {
    document.body.innerHTML = "";
  });
});

describe("App drawing intake", () => {
  it("renders single-shot drawing input with native capture hint", async () => {
    const { container } = await renderApp();

    const drawingInput = getDrawingInput(container);
    expect(drawingInput.getAttribute("accept")).toBe("image/*");
    expect(drawingInput.getAttribute("capture")).toBe("environment");
  });

  it("blocks startup and shows guidance when no drawing has been selected", async () => {
    const { container } = await renderApp();
    await setCheckboxValue(getConsentCheckbox(container), true);

    await clickButton(getStartButton(container));
    await flushPromises();

    expect(requestSessionStartMock).not.toHaveBeenCalled();
    expect(derivePersonaFromDrawingMock).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Capture or choose the drawing before starting.");
  });

  it("derives persona from the selected drawing instead of a placeholder path", async () => {
    const { container } = await renderApp();
    await setCheckboxValue(getConsentCheckbox(container), true);
    await selectDrawing(getDrawingInput(container), createDrawingFile());

    await clickButton(getStartButton(container));
    await flushPromises();

    expect(requestSessionStartMock).toHaveBeenCalledOnce();
    expect(derivePersonaFromDrawingMock).toHaveBeenCalledOnce();
    expect(derivePersonaFromDrawingMock).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: "session-123",
        drawingImageBase64: "aGVsbG8=",
        drawingMimeType: "image/png",
      })
    );
  });

  it("preserves session start before derivation and connects only after derivation resolves", async () => {
    const { container } = await renderApp();
    const order: string[] = [];
    const derivation = deferred<{ greetingText: string }>();

    requestSessionStartMock.mockImplementation(async () => {
      order.push("session_start");
      return "session-123";
    });
    derivePersonaFromDrawingMock.mockImplementation(async () => {
      order.push("persona_derivation_started");
      return derivation.promise;
    });
    buildLiveWebSocketUrlMock.mockImplementation(() => {
      order.push("websocket_url_built");
      return "ws://example.test/ws/live/session-123";
    });

    await setCheckboxValue(getConsentCheckbox(container), true);
    await selectDrawing(getDrawingInput(container), createDrawingFile());
    await clickButton(getStartButton(container));
    await flushPromises();

    expect(order).toEqual(["session_start", "persona_derivation_started"]);
    expect(buildLiveWebSocketUrlMock).not.toHaveBeenCalled();

    derivation.resolve({ greetingText: "Hi, Luna!" });
    await flushPromises();

    expect(order).toEqual([
      "session_start",
      "persona_derivation_started",
      "websocket_url_built",
    ]);
    expect(buildLiveWebSocketUrlMock).toHaveBeenCalledWith(
      expect.objectContaining({ sessionId: "session-123" })
    );
  });
});