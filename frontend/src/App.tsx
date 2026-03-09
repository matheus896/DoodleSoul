import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { extractPcmAudioChunksFromAdkEvent } from "./audio/adkEventAudio";
import { decodePcm16StreamChunk } from "./audio/pcm16Stream";
import { debugLog, getDebugRing } from "./media/debugSink";
import { parseMediaEvent } from "./media/mediaEventParser";
import { NarrativeTimeline } from "./media/NarrativeTimeline";
import { useMediaTimeline } from "./media/useMediaTimeline";
import { derivePersonaFromDrawing } from "./session/personaDerivation";
import {
  buildLiveWebSocketUrl,
  requestSessionStart,
  validateConsentForStart,
} from "./session/startSession";

export interface PlaybackMetrics {
  enqueuedChunks: number;
  totalEnqueuedSamples: number;
  workletBufferedSamples: number;
  workletUnderflowFrames: number;
  workletOverflowSamples: number;
  workletTotalWritten: number;
  workletTotalRead: number;
}

export type AppState = "idle" | "starting" | "deriving_persona" | "connecting" | "ready" | "error";

const stateText: Record<AppState, string> = {
  idle: "Waiting to start...",
  starting: "Starting session...",
  deriving_persona: "Creating magic...",
  connecting: "Connecting...",
  ready: "Ready!",
  error: "Error"
};

type AppWindow = Window & {
  __animismPlayerMetrics?: () => PlaybackMetrics;
  __animismSetupMetrics?: { setupTimeMs: number };
  __animismDebugRing?: () => ReturnType<typeof getDebugRing>;
};

interface SelectedDrawing {
  imageBase64: string;
  mimeType: string;
  fileName: string;
}

const DRAWING_REQUIRED_MESSAGE = "Capture or choose the drawing before starting.";
const INVALID_DRAWING_MESSAGE = "Select a valid image file for the drawing.";
const DRAWING_READ_ERROR_MESSAGE = "Could not read the drawing image. Please try again.";

function bytesToBase64(bytes: Uint8Array): string {
  const chunkSize = 0x8000;
  let binary = "";

  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }

  return btoa(binary);
}

async function readDrawingFile(file: File): Promise<SelectedDrawing> {
  if (!file.type.startsWith("image/")) {
    throw new Error("invalid_image_type");
  }

  const buffer = await file.arrayBuffer();

  return {
    imageBase64: bytesToBase64(new Uint8Array(buffer)),
    mimeType: file.type || "image/jpeg",
    fileName: file.name,
  };
}

export default function App() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [caregiverConsent, setCaregiverConsent] = useState(false);
  const [childName, setChildName] = useState("");
  const [selectedDrawing, setSelectedDrawing] = useState<SelectedDrawing | null>(null);
  const [initialGreeting, setInitialGreeting] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  const { scenes, dispatchMediaEvent, reset: resetTimeline } = useMediaTimeline();

  const captureContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const playbackNodeRef = useRef<AudioWorkletNode | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const downstreamCarryRef = useRef<Uint8Array>(new Uint8Array(0));

  const metricsRef = useRef<PlaybackMetrics>({
    enqueuedChunks: 0,
    totalEnqueuedSamples: 0,
    workletBufferedSamples: 0,
    workletUnderflowFrames: 0,
    workletOverflowSamples: 0,
    workletTotalWritten: 0,
    workletTotalRead: 0,
  });

  useEffect(() => {
    const appWindow = window as AppWindow;
    appWindow.__animismPlayerMetrics = () => {
      playbackNodeRef.current?.port.postMessage({ command: "getMetrics" });
      return { ...metricsRef.current };
    };
    appWindow.__animismDebugRing = getDebugRing;

    return () => {
      delete appWindow.__animismPlayerMetrics;
      delete appWindow.__animismDebugRing;
      websocketRef.current?.close();
      void captureContextRef.current?.close();
      void playbackContextRef.current?.close();
    };
  }, []);

  const sendSamplesToWorklet = (samples: Int16Array) => {
    const node = playbackNodeRef.current;
    if (!node || samples.length === 0) {
      return;
    }
    const copy = samples.buffer.slice(
      samples.byteOffset,
      samples.byteOffset + samples.byteLength
    );
    node.port.postMessage(copy, [copy]);

    metricsRef.current.enqueuedChunks += 1;
    metricsRef.current.totalEnqueuedSamples += samples.length;
  };

  const handleDrawingChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    if (!file) {
      setSelectedDrawing(null);
      return;
    }

    try {
      const drawing = await readDrawingFile(file);
      setSelectedDrawing(drawing);
      if (actionMessage) {
        setActionMessage("");
      }
      setAppState((current) => (current === "error" ? "idle" : current));
    } catch (error) {
      setSelectedDrawing(null);
      setAppState("error");
      setActionMessage(
        error instanceof Error && error.message === "invalid_image_type"
          ? INVALID_DRAWING_MESSAGE
          : DRAWING_READ_ERROR_MESSAGE
      );
    }
  };

  const start = async () => {
    if (appState !== "idle" && appState !== "error") {
      return;
    }

    const consentValidation = validateConsentForStart(caregiverConsent);
    if (!consentValidation.ok) {
      setAppState("error");
      setActionMessage(consentValidation.message);
      return;
    }

    if (!selectedDrawing) {
      setAppState("error");
      setActionMessage(DRAWING_REQUIRED_MESSAGE);
      return;
    }

    const startTime = performance.now();

    try {
      setAppState("starting");
      setActionMessage("");
      setInitialGreeting("");
      resetTimeline();

      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
      const wsUrlTemplate =
        (import.meta.env.VITE_WS_URL_TEMPLATE as string | undefined) ??
        (import.meta.env.VITE_WS_URL as string | undefined);
      const sessionId = await requestSessionStart(apiBaseUrl);
      const normalizedChildName = childName.trim();

      setAppState("deriving_persona");

      try {
        const personaResult = await derivePersonaFromDrawing({
          sessionId,
          drawingImageBase64: selectedDrawing.imageBase64,
          drawingMimeType: selectedDrawing.mimeType,
          childContext: normalizedChildName
            ? { childName: normalizedChildName }
            : undefined,
          apiBaseUrl,
        });
        setInitialGreeting(personaResult.greetingText);
      } catch {
        // Keep startup resilient even if derivation service is temporarily unavailable.
        setInitialGreeting("Hi, let's play together!");
      }
      const wsUrl = buildLiveWebSocketUrl({
        sessionId,
        apiBaseUrl,
        wsUrlTemplate,
      });

      setAppState("connecting");

      const captureContext = new AudioContext();
      captureContextRef.current = captureContext;
      await captureContext.resume();

      const playbackContext = new AudioContext({ sampleRate: 24000 });
      playbackContextRef.current = playbackContext;
      await playbackContext.resume();

      await playbackContext.audioWorklet.addModule(
        new URL("./audio/worklets/pcm-playback-worklet.ts", import.meta.url)
      );
      const playbackNode = new AudioWorkletNode(
        playbackContext,
        "pcm-playback-worklet"
      );
      playbackNode.connect(playbackContext.destination);
      playbackNodeRef.current = playbackNode;

      playbackNode.port.onmessage = (event: MessageEvent) => {
        const data = event.data as { type?: string } | undefined;
        if (data?.type === "metrics") {
          const m = data as unknown as {
            bufferedSamples: number;
            underflowFrames: number;
            overflowSamples: number;
            totalWritten: number;
            totalRead: number;
          };
          metricsRef.current.workletBufferedSamples = m.bufferedSamples;
          metricsRef.current.workletUnderflowFrames = m.underflowFrames;
          metricsRef.current.workletOverflowSamples = m.overflowSamples;
          metricsRef.current.workletTotalWritten = m.totalWritten;
          metricsRef.current.workletTotalRead = m.totalRead;
        }
      };

      await captureContext.audioWorklet.addModule(
        new URL("./audio/worklets/capture-worklet.ts", import.meta.url)
      );
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const source = captureContext.createMediaStreamSource(stream);
      const captureNode = new AudioWorkletNode(
        captureContext,
        "capture-worklet"
      );
      source.connect(captureNode);

      const websocket = new WebSocket(wsUrl);
      websocket.binaryType = "arraybuffer";
      websocketRef.current = websocket;
      downstreamCarryRef.current = new Uint8Array(0);
      let configSent = false;

      captureNode.port.onmessage = (event: MessageEvent) => {
        const data = event.data as {
          kind: string;
          sampleRate: number;
          channels: number;
          encoding: string;
          data: ArrayBuffer;
        };

        if (data.kind !== "pcm16" || websocket.readyState !== WebSocket.OPEN) {
          return;
        }

        if (!configSent) {
          websocket.send(
            JSON.stringify({
              type: "audio_config",
              sample_rate: data.sampleRate,
              channels: data.channels,
              encoding: data.encoding,
            })
          );
          configSent = true;
        }

        websocket.send(data.data);
      };

      websocket.onopen = () => {
        setAppState("ready");
        const setupTimeMs = performance.now() - startTime;
        (window as AppWindow).__animismSetupMetrics = { setupTimeMs };
        console.info("Setup metrics:", { setupTimeMs });
      };

      websocket.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
        if (typeof event.data === "string") {
          try {
            const parsed = JSON.parse(event.data) as unknown;

            // Debug: log raw WS text event (skip non-typed payloads)
            const parsedObj = parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : null;
            if (parsedObj?.type) {
              debugLog({
                event_type: "ws_text_received",
                source: "App",
                event_kind: String(parsedObj.type),
                scene_id: typeof parsedObj.scene_id === "string" ? parsedObj.scene_id : undefined,
              });
            }

            // Media events dispatched to NarrativeTimeline (F3.1/F3.2/F3.3)
            // parseMediaEvent logs drops to debugSink internally
            const mediaEvent = parseMediaEvent(parsed);
            if (mediaEvent) {
              debugLog({
                event_type: "media_event_dispatched",
                source: "App",
                scene_id: mediaEvent.scene_id,
                event_kind: mediaEvent.type,
              });
              dispatchMediaEvent(mediaEvent);
              return;
            }

            // Audio extraction (existing path)
            const chunks = extractPcmAudioChunksFromAdkEvent(parsed);
            for (const chunk of chunks) {
              const { samples, carry } = decodePcm16StreamChunk(
                chunk.buffer,
                downstreamCarryRef.current
              );
              downstreamCarryRef.current = carry;
              if (samples.length > 0) {
                sendSamplesToWorklet(samples);
              }
            }
          } catch {
            // Ignore malformed non-audio control payloads.
          }
          return;
        }
        const { samples, carry } = decodePcm16StreamChunk(
          event.data,
          downstreamCarryRef.current
        );
        downstreamCarryRef.current = carry;
        if (samples.length > 0) {
          sendSamplesToWorklet(samples);
        }
      };

      websocket.onerror = () => {
        setAppState("error");
        setActionMessage("Real-time connection failed. Please retry.");
      };

      websocket.onclose = () => {
        playbackNodeRef.current?.port.postMessage({ command: "getMetrics" });
        setTimeout(() => {
          console.info("PlaybackMetrics", { ...metricsRef.current });
        }, 100);
        setAppState((prev) => {
          if (prev !== "error") {
            setActionMessage("Session ended. Click Retry to connect again.");
          }
          return "error";
        });
      };
    } catch (error) {
      console.error("Session startup failed during audio/worklet setup.", error);
      setAppState("error");
      setActionMessage("Could not start session. Verify consent and try again.");
    }
  };

  const isLoading = appState !== "idle" && appState !== "ready" && appState !== "error";

  return (
    <main className="app-container">
      <h1 className="app-title">A(I)nimism Studio</h1>

      <div className="session-card">
        <div className="status-row">
          <p aria-live="polite" className="status-text">Status: {stateText[appState]}</p>
          {isLoading && (
            <div
              aria-busy="true"
              className="spinner"
            ></div>
          )}
        </div>

        <label className="input-label">
          <span className="input-label-text">Drawing Photo</span>
          <input
            className="file-input"
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(event) => {
              void handleDrawingChange(event);
            }}
          />
          <span aria-live="polite" className="file-input-hint">
            {selectedDrawing
              ? `Ready to wake up: ${selectedDrawing.fileName}`
              : "Use the camera or choose a photo of the drawing."}
          </span>
        </label>

        <label className="input-label">
          <span className="input-label-text">Child's Name (optional)</span>
          <input
            className="text-input"
            type="text"
            value={childName}
            onChange={(event) => setChildName(event.target.value)}
          />
        </label>
        <label className="consent-label">
          <input
            className="consent-checkbox"
            type="checkbox"
            checked={caregiverConsent}
            onChange={(event) => {
              setCaregiverConsent(event.target.checked);
              if (actionMessage) {
                setActionMessage("");
              }
            }}
          />
          <span className="consent-text">Caregiver consent confirmed</span>
        </label>
        {initialGreeting && (
          <p aria-live="polite" className="greeting-box">
            Greeting: {initialGreeting}
          </p>
        )}
        {actionMessage && (
          <p role="alert" className="error-alert">
            {actionMessage}
          </p>
        )}
      </div>

      <NarrativeTimeline scenes={scenes} />

      <button
        className="start-button"
        onClick={() => void start()}
        disabled={isLoading || appState === "ready"}
      >
        {appState === "error" ? "Retry" : "Start"}
      </button>
    </main>
  );
}
