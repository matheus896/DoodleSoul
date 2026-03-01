import { expect, test } from "@playwright/test";

async function installMediaAndSocketMocks(page: Parameters<typeof test>[0]["page"], mode: "open" | "error") {
  await page.addInitScript((mockMode) => {
    const globalAny = window as unknown as {
      __mockWebSocketSent: Array<ArrayBuffer | string>;
      __emitWorkletChunk: (() => void) | null;
      __mockSocketMode: "open" | "error";
    };

    globalAny.__mockSocketMode = mockMode;
    globalAny.__mockWebSocketSent = [];
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

  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByText("Status: Vivo")).toBeVisible();

  await page.evaluate(() => {
    (window as unknown as { __emitWorkletChunk: (() => void) | null }).__emitWorkletChunk?.();
  });

  const sentPayloads = await page.evaluate(() => {
    return (window as unknown as { __mockWebSocketSent: Array<ArrayBuffer | string> }).__mockWebSocketSent;
  });

  expect(sentPayloads.length).toBe(2);
  expect(typeof sentPayloads[0]).toBe("string");
});


test("start flow transitions to error state on websocket failure", async ({ page }) => {
  await installMediaAndSocketMocks(page, "error");
  await page.goto("/");

  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByText("Status: Erro")).toBeVisible();
});
