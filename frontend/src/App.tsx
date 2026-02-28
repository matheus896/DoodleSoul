import { useEffect, useRef, useState } from "react";

import { extractPcmAudioChunksFromAdkEvent } from "./audio/adkEventAudio";
import { decodePcm16StreamChunk } from "./audio/pcm16Stream";
import { Pcm24kPlayer } from "./audio/pcmPlayer";

type AppWindow = Window & {
  __animismPlayerMetrics?: () => ReturnType<Pcm24kPlayer["getMetrics"]>;
};

export default function App() {
  const [status, setStatus] = useState("Conectando");
  const [started, setStarted] = useState(false);

  const audioContextRef = useRef<AudioContext | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const playerRef = useRef(new Pcm24kPlayer(24000 * 2, 24000));
  const downstreamCarryRef = useRef<Uint8Array>(new Uint8Array(0));
  const downstreamSampleRateRef = useRef(24000);
  const schedulerRef = useRef<number | null>(null);
  const nextPlaybackTimeRef = useRef(0);

  useEffect(() => {
    const appWindow = window as AppWindow;
    appWindow.__animismPlayerMetrics = () => playerRef.current.getMetrics();

    return () => {
      delete appWindow.__animismPlayerMetrics;
      if (schedulerRef.current !== null) {
        window.clearInterval(schedulerRef.current);
      }
      websocketRef.current?.close();
      void audioContextRef.current?.close();
    };
  }, []);

  const ensurePlaybackScheduler = (context: AudioContext) => {
    if (schedulerRef.current !== null) {
      return;
    }

    schedulerRef.current = window.setInterval(() => {
      const playbackRate = downstreamSampleRateRef.current;
      const pullSamples = Math.max(1, Math.round(playbackRate / 50));
      const chunk = playerRef.current.pullChunk(pullSamples);
      if (chunk.length === 0) {
        return;
      }

      const output = new Float32Array(chunk.length);
      for (let index = 0; index < chunk.length; index += 1) {
        output[index] = (chunk[index] ?? 0) / 32768;
      }

      const buffer = context.createBuffer(1, output.length, playbackRate);
      buffer.copyToChannel(output, 0);

      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);

      const now = context.currentTime;
      if (nextPlaybackTimeRef.current < now) {
        nextPlaybackTimeRef.current = now;
      }
      source.start(nextPlaybackTimeRef.current);
      nextPlaybackTimeRef.current += buffer.duration;
    }, 20);
  };

  const start = async () => {
    if (started) {
      return;
    }

    try {
      setStarted(true);
      setStatus("Conectando");

      const context = new AudioContext();
      audioContextRef.current = context;
      await context.resume();

      const wsUrl = import.meta.env.VITE_WS_URL as string | undefined;
      if (!wsUrl) {
        setStatus("Vivo");
        return;
      }

      await context.audioWorklet.addModule(new URL("./audio/worklets/capture-worklet.ts", import.meta.url));
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const source = context.createMediaStreamSource(stream);
      const captureNode = new AudioWorkletNode(context, "capture-worklet");
      source.connect(captureNode);

      ensurePlaybackScheduler(context);

      const websocket = new WebSocket(wsUrl);
      websocket.binaryType = "arraybuffer";
      websocketRef.current = websocket;
      downstreamCarryRef.current = new Uint8Array(0);
      downstreamSampleRateRef.current = 24000;
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
              encoding: data.encoding
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
              if (chunk.sampleRate) {
                downstreamSampleRateRef.current = chunk.sampleRate;
              }
              const { samples, carry } = decodePcm16StreamChunk(
                chunk.buffer,
                downstreamCarryRef.current
              );
              downstreamCarryRef.current = carry;
              if (samples.length > 0) {
                playerRef.current.enqueue(samples);
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
          playerRef.current.enqueue(samples);
        }
      };

      websocket.onerror = () => {
        setStatus("Erro");
      };

      websocket.onclose = () => {
        console.info("PlayerMetrics", playerRef.current.getMetrics());
        if (status !== "Erro") {
          setStatus("Erro");
        }
      };
    } catch {
      setStatus("Erro");
      setStarted(false);
    }
  };

  return (
    <main>
      <h1>A(I)nimism Studio</h1>
      <p aria-live="polite">Status: {status}</p>
      <button onClick={() => void start()} disabled={started && status === "Vivo"}>
        Start
      </button>
    </main>
  );
}
