import { expect, test } from "@playwright/test";

async function installMediaAndSocketMocks(page: Parameters<typeof test>[0]["page"], mode: "open" | "error") {
  await page.addInitScript((mockMode) => {
    const globalAny = window as unknown as {
      __mockWebSocketSent: Array<ArrayBuffer | string>;
      __mockWebSocketUrls: string[];
      __mockFetchCalls: Array<{ url: string; body: unknown }>;
      __emitWorkletChunk: (() => void) | null;
      __mockSocketMode: "open" | "error";
    };

    globalAny.__mockSocketMode = mockMode;
    globalAny.__mockWebSocketSent = [];
    globalAny.__mockWebSocketUrls = [];
    globalAny.__mockFetchCalls = [];
    globalAny.__emitWorkletChunk = null;

    class MockAudioContext {
      public currentTime = 0;
      public destination = {};
      public audioWorklet = {
        addModule: async () => undefined
      };

      async resume() {
        return undefined;
      }

      async close() {
        return undefined;
      }

      createMediaStreamSource() {
        return {
          connect: () => undefined
        };
      }

      createBuffer(_channels: number, length: number, _sampleRate: number) {
        return {
          duration: length / 24000,
          copyToChannel: () => undefined
        };
      }

      createBufferSource() {
        return {
          buffer: null,
          connect: () => undefined,
          start: () => undefined
        };
      }
    }

    class MockAudioWorkletNode {
      public port = {
        onmessage: null as ((event: MessageEvent) => void) | null,
        postMessage: (_data: unknown, _transfer?: Transferable[]) => undefined
      };

      constructor(_context: unknown, name?: string) {
        if (name === "capture-worklet") {
          globalAny.__emitWorkletChunk = () => {
            this.port.onmessage?.(
              {
                data: {
                  kind: "pcm16",
                  sampleRate: 16000,
                  channels: 1,
                  encoding: "pcm_s16le",
                  data: new Int16Array([1, 2, 3, 4]).buffer
                }
              } as MessageEvent
            );
          };
        }
      }

      connect() {
        return undefined;
      }
    }

    class MockWebSocket {
      static OPEN = 1;
      static CLOSED = 3;
      public readyState = 0;
      public binaryType = "blob";
      public onopen: (() => void) | null = null;
      public onmessage: ((event: MessageEvent<ArrayBuffer | string>) => void) | null = null;
      public onerror: (() => void) | null = null;
      public onclose: (() => void) | null = null;

      constructor(_url: string) {
        globalAny.__mockWebSocketUrls.push(_url);
        queueMicrotask(() => {
          if (globalAny.__mockSocketMode === "error") {
            this.readyState = MockWebSocket.CLOSED;
            this.onerror?.();
            this.onclose?.();
            return;
          }

          this.readyState = MockWebSocket.OPEN;
          this.onopen?.();
          const response = new Int16Array([10, 11, 12]).buffer;
          this.onmessage?.({ data: response } as MessageEvent<ArrayBuffer>);
        });
      }

      send(payload: ArrayBuffer | string) {
        globalAny.__mockWebSocketSent.push(payload);
      }

      close() {
        this.readyState = MockWebSocket.CLOSED;
        this.onclose?.();
      }
    }

    Object.defineProperty(window, "AudioContext", {
      value: MockAudioContext,
      writable: true
    });
    Object.defineProperty(window, "AudioWorkletNode", {
      value: MockAudioWorkletNode,
      writable: true
    });
    Object.defineProperty(window, "WebSocket", {
      value: MockWebSocket,
      writable: true
    });
    Object.defineProperty(window, "fetch", {
      value: async (url: string, init?: RequestInit) => {
        const parsedBody = init?.body
          ? JSON.parse(String(init.body))
          : null;
        globalAny.__mockFetchCalls.push({
          url,
          body: parsedBody,
        });

        if (url.includes("/persona/derive")) {
          return {
            ok: true,
            json: async () => ({
              status: "ok",
              data: {
                session_id: "session-e2e-123",
                persona_source: "drawing_derived",
                fallback_applied: false,
                voice_traits: ["playful"],
                personality_traits: ["kind"],
                greeting_text: "Oi Luna, sou seu amigo do desenho!"
              }
            })
          };
        }

        return {
          ok: true,
          json: async () => ({
            status: "ok",
            data: {
              session_id: "session-e2e-123",
              consent_captured: true,
              consent_captured_at: "2026-03-01T00:00:00Z"
            }
          })
        };
      },
      writable: true
    });

    Object.defineProperty(navigator, "mediaDevices", {
      value: {
        getUserMedia: async () => ({ getTracks: () => [] })
      },
      configurable: true
    });
  }, mode);
}


test("start flow transitions to live state", async ({ page }) => {
  await installMediaAndSocketMocks(page, "open");
  await page.goto("/");

  await page.getByLabel("Nome da crianca (opcional)").fill("Luna");
  await page.getByRole("checkbox", { name: "Consentimento do cuidador confirmado" }).check();
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByText("Status: Vivo")).toBeVisible();
  await expect(page.getByText("Saudacao inicial: Oi Luna, sou seu amigo do desenho!")).toBeVisible();

  await page.evaluate(() => {
    (window as unknown as { __emitWorkletChunk: (() => void) | null }).__emitWorkletChunk?.();
  });

  const sentPayloads = await page.evaluate(() => {
    return (window as unknown as { __mockWebSocketSent: Array<ArrayBuffer | string> }).__mockWebSocketSent;
  });
  const wsUrls = await page.evaluate(() => {
    return (window as unknown as { __mockWebSocketUrls: string[] }).__mockWebSocketUrls;
  });
  const fetchCalls = await page.evaluate(() => {
    return (window as unknown as {
      __mockFetchCalls: Array<{ url: string; body: { child_context?: { child_name?: string } } }>;
    }).__mockFetchCalls;
  });
  const liveWsUrls = wsUrls.filter((url) => url.includes("/ws/live/"));
  const personaCall = fetchCalls.find((call) => call.url.includes("/persona/derive"));

  expect(sentPayloads.length).toBe(2);
  expect(typeof sentPayloads[0]).toBe("string");
  expect(liveWsUrls.some((url) => url.includes("/ws/live/session-e2e-123"))).toBe(
    true
  );
  expect(personaCall?.body.child_context?.child_name).toBe("Luna");
});


test("start flow transitions to error state on websocket failure", async ({ page }) => {
  await installMediaAndSocketMocks(page, "error");
  await page.goto("/");

  await page.getByRole("checkbox", { name: "Consentimento do cuidador confirmado" }).check();
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByText("Status: Erro")).toBeVisible();
});


test("start flow blocks when consent is not confirmed", async ({ page }) => {
  await installMediaAndSocketMocks(page, "open");
  await page.goto("/");

  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByText("Status: Erro")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("consentimento");

  const wsUrls = await page.evaluate(() => {
    return (window as unknown as { __mockWebSocketUrls: string[] }).__mockWebSocketUrls;
  });
  const liveWsUrls = wsUrls.filter((url) => url.includes("/ws/live/"));
  expect(liveWsUrls).toHaveLength(0);
});
