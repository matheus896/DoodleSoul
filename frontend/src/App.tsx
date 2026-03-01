import { useEffect, useRef, useState } from "react";

import { extractPcmAudioChunksFromAdkEvent } from "./audio/adkEventAudio";
import { decodePcm16StreamChunk } from "./audio/pcm16Stream";
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

type AppWindow = Window & {
  __animismPlayerMetrics?: () => PlaybackMetrics;
};

export default function App() {
  const [status, setStatus] = useState("Conectando");
  const [started, setStarted] = useState(false);
  const [caregiverConsent, setCaregiverConsent] = useState(false);
  const [actionMessage, setActionMessage] = useState("");

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

    return () => {
      delete appWindow.__animismPlayerMetrics;
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

  const start = async () => {
    if (started) {
      return;
    }

    const consentValidation = validateConsentForStart(caregiverConsent);
    if (!consentValidation.ok) {
      setStatus("Erro");
      setActionMessage(consentValidation.message);
      return;
    }

    try {
      setStarted(true);
      setStatus("Conectando");
      setActionMessage("");

      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
      const wsUrlTemplate =
        (import.meta.env.VITE_WS_URL_TEMPLATE as string | undefined) ??
        (import.meta.env.VITE_WS_URL as string | undefined);
      const sessionId = await requestSessionStart(apiBaseUrl);
      const wsUrl = buildLiveWebSocketUrl({
        sessionId,
        apiBaseUrl,
        wsUrlTemplate,
      });

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
        setStatus("Vivo");
      };

      websocket.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
        if (typeof event.data === "string") {
          try {
            const parsed = JSON.parse(event.data) as unknown;
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
        setStatus("Erro");
        setActionMessage("Falha na conexao em tempo real. Tente novamente.");
      };

      websocket.onclose = () => {
        playbackNodeRef.current?.port.postMessage({ command: "getMetrics" });
        setTimeout(() => {
          console.info("PlaybackMetrics", { ...metricsRef.current });
        }, 100);
        if (status !== "Erro") {
          setStatus("Erro");
          setActionMessage("Sessao encerrada. Clique em Start para tentar novamente.");
        }
      };
    } catch {
      setStatus("Erro");
      setStarted(false);
      setActionMessage("Nao foi possivel iniciar a sessao. Verifique o consentimento e tente novamente.");
    }
  };

  return (
    <main>
      <h1>A(I)nimism Studio</h1>
      <p aria-live="polite">Status: {status}</p>
      <label>
        <input
          type="checkbox"
          checked={caregiverConsent}
          onChange={(event) => {
            setCaregiverConsent(event.target.checked);
            if (actionMessage) {
              setActionMessage("");
            }
          }}
        />
        {" "}Consentimento do cuidador confirmado
      </label>
      {actionMessage && <p role="alert">{actionMessage}</p>}
      <button
        onClick={() => void start()}
        disabled={started && status === "Vivo"}
      >
        Start
      </button>
    </main>
  );
}
