/**
 * ChildSessionPage — /session
 *
 * Polished child-facing view. Wraps all existing audio/WebSocket/timeline
 * logic from the original App.tsx with the DoodleSoul design system UI.
 * Two sub-views rendered via local state:
 *   "setup"  → MagicalSetup (drawing upload + consent)
 *   "session" → Live session with NarrativeTimeline
 */

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Mic, MicOff, Sparkles, ImagePlus, Play, RefreshCw, HelpCircle } from "lucide-react";

import { extractPcmAudioChunksFromAdkEvent } from "../audio/adkEventAudio";
import { decodePcm16StreamChunk } from "../audio/pcm16Stream";
import { debugLog, getDebugRing } from "../media/debugSink";
import { parseMediaEvent } from "../media/mediaEventParser";
import { NarrativeTimeline } from "../media/NarrativeTimeline";
import { useMediaTimeline } from "../media/useMediaTimeline";
import { derivePersonaFromDrawing } from "../session/personaDerivation";
import { writeActiveSessionId } from "../session/sessionStorage";
import {
  buildLiveWebSocketUrl,
  requestSessionStart,
  validateConsentForStart,
  requestSessionEnd,
} from "../session/startSession";

/* ── Types ── */
export interface PlaybackMetrics {
  enqueuedChunks: number;
  totalEnqueuedSamples: number;
  workletBufferedSamples: number;
  workletUnderflowFrames: number;
  workletOverflowSamples: number;
  workletTotalWritten: number;
  workletTotalRead: number;
}

export type AppState =
  | "idle"
  | "starting"
  | "deriving_persona"
  | "connecting"
  | "ready"
  | "error";

type AppWindow = Window & {
  __animismPlayerMetrics?: () => PlaybackMetrics;
  __animismSetupMetrics?: { setupTimeMs: number };
  __animismDebugRing?: () => ReturnType<typeof getDebugRing>;
};

interface SelectedDrawing {
  imageBase64: string;
  mimeType: string;
  fileName: string;
  previewUrl: string;
}

function bytesToBase64(bytes: Uint8Array): string {
  const chunkSize = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

async function readDrawingFile(file: File): Promise<SelectedDrawing> {
  if (!file.type.startsWith("image/")) throw new Error("invalid_image_type");
  const buffer = await file.arrayBuffer();
  return {
    imageBase64: bytesToBase64(new Uint8Array(buffer)),
    mimeType: file.type || "image/jpeg",
    fileName: file.name,
    previewUrl: URL.createObjectURL(file),
  };
}

/* ── Setup step progress labels ── */
const SETUP_STEPS = [
  "Preparing your magical world…",
  "Bringing your drawing to life…",
  "Creating story world…",
  "Almost ready!",
];

/* ── Progress circle component ── */
function ProcessingCircle({ progress }: { progress: number }) {
  return (
    <div
      style={{
        position: "relative",
        width: 180,
        height: 180,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {/* Outer glow ring */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: "50%",
          background: "rgba(249,115,22,.12)",
          animation: "gentle-pulse 2s ease-in-out infinite",
        }}
      />
      {/* SVG progress arc */}
      <svg
        width="180"
        height="180"
        style={{ position: "absolute", inset: 0, transform: "rotate(-90deg)" }}
      >
        <circle cx="90" cy="90" r="78" fill="none" stroke="#FED7AA" strokeWidth="6" />
        <circle
          cx="90"
          cy="90"
          r="78"
          fill="none"
          stroke="#F97316"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${2 * Math.PI * 78}`}
          strokeDashoffset={`${2 * Math.PI * 78 * (1 - progress / 100)}`}
          style={{ transition: "stroke-dashoffset .6s ease" }}
        />
      </svg>
      {/* Inner orange button */}
      <div
        style={{
          width: 130,
          height: 130,
          borderRadius: "50%",
          background: "linear-gradient(145deg, #FB923C, #EA580C)",
          boxShadow: "0 8px 24px rgba(234,88,12,.5), inset 0 2px 4px rgba(255,255,255,.2)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 4,
          animation: "processing-pulse 2s ease-in-out infinite",
        }}
      >
        <Sparkles size={32} color="#fff" strokeWidth={2.5} />
        <span
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "0.75rem",
            fontWeight: 700,
            color: "#fff",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          PROCESSING
        </span>
      </div>
      {/* Star accent */}
      <div
        style={{
          position: "absolute",
          bottom: 8,
          right: 8,
          width: 28,
          height: 28,
          borderRadius: "50%",
          background: "#fff",
          boxShadow: "0 2px 8px rgba(249,115,22,.3)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <span style={{ fontSize: 16 }}>⭐</span>
      </div>
    </div>
  );
}

/* ── Magical Setup view ── */
interface SetupViewProps {
  childName: string;
  setChildName: (v: string) => void;
  caregiverConsent: boolean;
  setCaregiverConsent: (v: boolean) => void;
  selectedDrawing: SelectedDrawing | null;
  onDrawingChange: (e: ChangeEvent<HTMLInputElement>) => void;
  onStart: () => void;
  appState: AppState;
  actionMessage: string;
}

function SetupView({
  childName,
  setChildName,
  caregiverConsent,
  setCaregiverConsent,
  selectedDrawing,
  onDrawingChange,
  onStart,
  appState,
  actionMessage,
}: SetupViewProps) {
  const isLoading =
    appState !== "idle" && appState !== "ready" && appState !== "error";

  const stepIndex = {
    idle: -1,
    starting: 0,
    deriving_persona: 1,
    connecting: 2,
    ready: 3,
    error: -1,
  }[appState];

  const progress = stepIndex >= 0 ? (stepIndex + 1) * 25 : 0;
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(160deg, #FFF7ED 0%, #FEFCE8 40%, #EEF2FF 100%)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "2.5rem 1.25rem 3rem",
        fontFamily: "var(--font-body)",
      }}
    >
      {/* Logo */}
      <div style={{ marginBottom: "1.5rem", display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: "50%",
            background: "linear-gradient(135deg, #FB923C, #F97316)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 4px 12px rgba(249,115,22,.35)",
          }}
        >
          <Sparkles size={22} color="#fff" strokeWidth={2.5} />
        </div>
        <span
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "1.5rem",
            fontWeight: 700,
            color: "var(--color-foreground)",
          }}
        >
          DoodleSoul
        </span>
      </div>

      {/* Heading */}
      <h1
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "clamp(1.75rem, 5vw, 2.5rem)",
          fontWeight: 700,
          color: "var(--color-foreground)",
          textAlign: "center",
          marginBottom: "0.5rem",
          lineHeight: 1.2,
        }}
      >
        The Magical Setup
      </h1>

      {/* Speech bubble or status */}
      {isLoading ? (
        <>
          <div
            style={{
              background: "#fff",
              border: "1px solid #E2E8F0",
              borderRadius: "var(--radius-xl)",
              padding: "0.875rem 1.5rem",
              maxWidth: 340,
              textAlign: "center",
              fontSize: "1rem",
              fontWeight: 500,
              color: "var(--color-foreground)",
              marginBottom: "1.75rem",
              boxShadow: "0 2px 8px rgba(0,0,0,.06)",
              position: "relative",
            }}
          >
            {SETUP_STEPS[Math.max(0, stepIndex)] ?? "Wait a second… the magic is happening!"}
            {/* Triangle */}
            <div
              style={{
                position: "absolute",
                bottom: -10,
                left: "50%",
                transform: "translateX(-50%)",
                width: 0,
                height: 0,
                borderLeft: "10px solid transparent",
                borderRight: "10px solid transparent",
                borderTop: "10px solid #fff",
              }}
            />
          </div>

          <ProcessingCircle progress={progress} />

          {/* Step card */}
          <div
            style={{
              marginTop: "2rem",
              background: "#fff",
              borderRadius: "var(--radius-xl)",
              padding: "1.25rem 1.5rem",
              width: "100%",
              maxWidth: 340,
              boxShadow: "0 2px 12px rgba(0,0,0,.06)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                marginBottom: 8,
              }}
            >
              <div>
                <div style={{ fontWeight: 700, fontSize: "1rem", color: "var(--color-foreground)" }}>
                  {SETUP_STEPS[Math.max(0, stepIndex)]}
                </div>
                <div style={{ fontSize: "0.8125rem", color: "var(--color-muted)", marginTop: 2 }}>
                  Step {stepIndex + 1} of 4
                </div>
              </div>
              <span
                style={{
                  fontFamily: "var(--font-display)",
                  fontWeight: 700,
                  fontSize: "1.25rem",
                  color: "var(--color-brand)",
                }}
              >
                {progress}%
              </span>
            </div>
            {/* Progress bar */}
            <div
              style={{
                height: 8,
                background: "#F1F5F9",
                borderRadius: 99,
                overflow: "hidden",
                marginBottom: 8,
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${progress}%`,
                  background: "linear-gradient(90deg, #FB923C, #F97316)",
                  borderRadius: 99,
                  transition: "width .6s ease",
                }}
              />
            </div>
            <p style={{ fontSize: "0.8125rem", color: "var(--color-muted)", textAlign: "center" }}>
              Our doodles are busy building your safe space…
            </p>
          </div>
        </>
      ) : (
        <>
          {/* Idle / error state — show the form */}
          <p
            style={{
              fontSize: "1rem",
              color: "var(--color-muted)",
              textAlign: "center",
              maxWidth: 320,
              marginBottom: "2rem",
              lineHeight: 1.6,
            }}
          >
            Upload your child's drawing and let the adventure begin!
          </p>

          {/* Drawing upload card */}
          <div
            style={{
              width: "100%",
              maxWidth: 360,
              background: "#fff",
              borderRadius: "var(--radius-2xl)",
              boxShadow: "var(--shadow-card)",
              border: "2px solid #E0E7FF",
              padding: "1.5rem",
              marginBottom: "1rem",
            }}
          >
            {/* Drawing preview or upload area */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              style={{
                width: "100%",
                height: 180,
                borderRadius: "var(--radius-xl)",
                border: `2px dashed ${selectedDrawing ? "#A5B4FC" : "#C7D2FE"}`,
                background: selectedDrawing ? "transparent" : "#EEF2FF",
                cursor: "pointer",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                overflow: "hidden",
                padding: 0,
                marginBottom: "1rem",
                transition: "border-color .2s",
              }}
              aria-label="Upload drawing"
            >
              {selectedDrawing ? (
                <img
                  src={selectedDrawing.previewUrl}
                  alt="Selected drawing preview"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : (
                <>
                  <ImagePlus size={32} color="#818CF8" strokeWidth={1.5} />
                  <span
                    style={{
                      fontFamily: "var(--font-display)",
                      fontSize: "1rem",
                      fontWeight: 600,
                      color: "#6366F1",
                    }}
                  >
                    Upload Drawing
                  </span>
                  <span style={{ fontSize: "0.8125rem", color: "var(--color-muted)" }}>
                    Tap to choose or take a photo
                  </span>
                </>
              )}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              style={{ display: "none" }}
              onChange={onDrawingChange}
              aria-label="Drawing image file input"
            />

            {/* Child name */}
            <label
              style={{ display: "block", marginBottom: "0.75rem" }}
            >
              <span
                style={{
                  display: "block",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  color: "#4338CA",
                  marginBottom: 4,
                }}
              >
                Child's Name (optional)
              </span>
              <input
                type="text"
                value={childName}
                onChange={(e) => setChildName(e.target.value)}
                placeholder="e.g. Leo"
                style={{
                  width: "100%",
                  padding: "0.625rem 0.875rem",
                  borderRadius: "var(--radius-lg)",
                  border: "2px solid #E0E7FF",
                  outline: "none",
                  fontFamily: "var(--font-body)",
                  fontSize: "0.9375rem",
                  color: "var(--color-foreground)",
                  background: "#FAFAFA",
                  transition: "border-color .2s",
                }}
              />
            </label>

            {/* Consent */}
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: "pointer",
                padding: "0.625rem 0.75rem",
                borderRadius: "var(--radius-lg)",
                background: "#EEF2FF",
                border: "1px solid #C7D2FE",
              }}
            >
              <input
                type="checkbox"
                checked={caregiverConsent}
                onChange={(e) => setCaregiverConsent(e.target.checked)}
                style={{
                  width: 18,
                  height: 18,
                  accentColor: "#4F46E5",
                  flexShrink: 0,
                }}
              />
              <span style={{ fontSize: "0.875rem", fontWeight: 500, color: "#3730A3" }}>
                Caregiver consent confirmed
              </span>
            </label>

            {/* Error message */}
            {actionMessage && (
              <div
                role="alert"
                style={{
                  marginTop: "0.75rem",
                  padding: "0.75rem",
                  borderRadius: "var(--radius-lg)",
                  background: "#FEF2F2",
                  border: "1px solid #FECACA",
                  color: "#DC2626",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                }}
              >
                {actionMessage}
              </div>
            )}
          </div>

          {/* Start button */}
          <button
            type="button"
            onClick={onStart}
            disabled={isLoading}
            style={{
              width: "100%",
              maxWidth: 360,
              padding: "1rem",
              background: "linear-gradient(135deg, #FB923C, #F97316)",
              color: "#fff",
              fontFamily: "var(--font-display)",
              fontSize: "1.125rem",
              fontWeight: 700,
              border: "none",
              borderRadius: "var(--radius-xl)",
              cursor: "pointer",
              boxShadow: "0 4px 0 0 #C2410C, 0 8px 24px rgba(234,88,12,.3)",
              transition: "transform .1s, box-shadow .1s",
              letterSpacing: "0.02em",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
            }}
            onMouseDown={(e) => {
              (e.currentTarget as HTMLButtonElement).style.transform = "translateY(2px)";
              (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 2px 0 0 #C2410C";
            }}
            onMouseUp={(e) => {
              (e.currentTarget as HTMLButtonElement).style.transform = "";
              (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 4px 0 0 #C2410C, 0 8px 24px rgba(234,88,12,.3)";
            }}
          >
            {appState === "error" ? (
              <><RefreshCw size={18} /> Retry Adventure</>
            ) : (
              <><Play size={18} fill="#fff" /> Start Adventure</>
            )}
          </button>
        </>
      )}

      {/* Branding footer */}
      <div
        style={{
          marginTop: "auto",
          paddingTop: "2.5rem",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 4,
        }}
      >
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: "50%",
            background: "#fff",
            boxShadow: "0 2px 12px rgba(0,0,0,.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Sparkles size={24} color="#F97316" strokeWidth={1.5} />
        </div>
        <span style={{ fontSize: "0.6875rem", letterSpacing: "0.12em", color: "var(--color-muted)", textTransform: "uppercase", fontWeight: 600 }}>
          Doodle Soul Engine
        </span>
      </div>

      <button
        type="button"
        style={{
          marginTop: "1rem",
          background: "none",
          border: "none",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 4,
          color: "var(--color-muted)",
          fontSize: "0.875rem",
        }}
      >
        <HelpCircle size={14} />
        Need help?
      </button>
    </div>
  );
}

/* ── Live session view (after "ready") ── */
interface LiveViewProps {
  childName: string;
  selectedDrawing: SelectedDrawing | null;
  initialGreeting: string;
  scenes: ReturnType<typeof useMediaTimeline>["scenes"];
  isMicActive: boolean;
  sessionDuration: number;
  onEndSession: () => void;
}

function LiveView({
  childName,
  selectedDrawing,
  initialGreeting,
  scenes,
  isMicActive,
  sessionDuration,
  onEndSession,
}: LiveViewProps) {
  const minutes = String(Math.floor(sessionDuration / 60)).padStart(2, "0");
  const seconds = String(sessionDuration % 60).padStart(2, "0");

  return (
    <div
      style={{
        height: "100vh",
        overflow: "hidden",
        background: "linear-gradient(160deg, #FFF7ED 0%, #EEF2FF 100%)",
        display: "flex",
        flexDirection: "column",
        fontFamily: "var(--font-body)",
      }}
    >
      {/* Header */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "1rem 1.25rem",
          background: "#fff",
          borderBottom: "1px solid #E2E8F0",
          boxShadow: "0 1px 4px rgba(0,0,0,.04)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: "50%",
              background: "linear-gradient(135deg, #FB923C, #F97316)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Sparkles size={18} color="#fff" strokeWidth={2.5} />
          </div>
          <span
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "1.125rem",
              fontWeight: 700,
              color: "var(--color-foreground)",
            }}
          >
            DoodleSoul
          </span>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0.375rem 0.875rem",
            background: "#F0FDF4",
            borderRadius: "var(--radius-full)",
            border: "1px solid #BBF7D0",
          }}
        >
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "#16A34A",
              animation: "gentle-pulse 2s ease-in-out infinite",
            }}
          />
          <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "#15803D" }}>
            Session Active: {minutes}:{seconds}
          </span>
        </div>
        <button
          type="button"
          onClick={onEndSession}
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: "#FEF2F2",
            border: "1px solid #FECACA",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#DC2626",
          }}
          title="End session"
          aria-label="End session"
        >
          <MicOff size={16} />
        </button>
      </header>

      <div style={{ flex: 1, padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem", overflowY: "auto" }}>
        {/* Persona card */}
        <div
          style={{
            background: "#fff",
            borderRadius: "var(--radius-2xl)",
            boxShadow: "var(--shadow-card)",
            border: "2px solid #E0E7FF",
            padding: "1.25rem",
            display: "flex",
            gap: "1rem",
            alignItems: "flex-start",
          }}
        >
          {/* Drawing preview */}
          {selectedDrawing ? (
            <div
              style={{
                width: 80,
                height: 80,
                borderRadius: "var(--radius-lg)",
                overflow: "hidden",
                border: "2px solid #C7D2FE",
                flexShrink: 0,
              }}
            >
              <img
                src={selectedDrawing.previewUrl}
                alt="Child's drawing"
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            </div>
          ) : (
            <div
              style={{
                width: 80,
                height: 80,
                borderRadius: "var(--radius-lg)",
                background: "#EEF2FF",
                border: "2px solid #C7D2FE",
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <ImagePlus size={28} color="#818CF8" strokeWidth={1.5} />
            </div>
          )}
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontSize: "0.6875rem",
                fontWeight: 700,
                letterSpacing: "0.1em",
                color: "#6366F1",
                textTransform: "uppercase",
                marginBottom: 4,
              }}
            >
              Drawing Derived Persona
            </div>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontSize: "1.25rem",
                fontWeight: 700,
                color: "var(--color-foreground)",
                marginBottom: 6,
              }}
            >
              {childName ? `${childName}'s Character` : "Your Character"}
            </div>
            {initialGreeting && (
              <div
                style={{
                  background: "#EEF2FF",
                  borderRadius: "var(--radius-lg)",
                  padding: "0.5rem 0.75rem",
                  fontSize: "0.875rem",
                  color: "#3730A3",
                  lineHeight: 1.5,
                }}
              >
                "{initialGreeting}"
              </div>
            )}
          </div>
        </div>

        {/* Mic indicator */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0.75rem 1rem",
            borderRadius: "var(--radius-xl)",
            background: isMicActive ? "#F0FDF4" : "#FEF2F2",
            border: `1px solid ${isMicActive ? "#BBF7D0" : "#FECACA"}`,
          }}
        >
          {isMicActive ? (
            <Mic size={18} color="#16A34A" />
          ) : (
            <MicOff size={18} color="#DC2626" />
          )}
          <span
            style={{
              fontSize: "0.875rem",
              fontWeight: 600,
              color: isMicActive ? "#15803D" : "#DC2626",
            }}
          >
            {isMicActive ? "Listening to your story…" : "Microphone inactive"}
          </span>
        </div>

        {/* Narrative timeline */}
        <NarrativeTimeline scenes={scenes} />
      </div>
    </div>
  );
}

/* ── Main ChildSessionPage ── */
export default function ChildSessionPage() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [caregiverConsent, setCaregiverConsent] = useState(false);
  const [childName, setChildName] = useState("");
  const [selectedDrawing, setSelectedDrawing] = useState<SelectedDrawing | null>(null);
  const [initialGreeting, setInitialGreeting] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [sessionDuration, setSessionDuration] = useState(0);
  const [activeSessionId, setActiveSessionId] = useState("");

  const { scenes, dispatchMediaEvent, reset: resetTimeline } = useMediaTimeline();

  const captureContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const playbackNodeRef = useRef<AudioWorkletNode | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const downstreamCarryRef = useRef<Uint8Array>(new Uint8Array(0));
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  // Session duration timer
  useEffect(() => {
    if (appState === "ready") {
      timerRef.current = setInterval(() => setSessionDuration((d) => d + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      if (appState === "idle") setSessionDuration(0);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [appState]);

  const sendSamplesToWorklet = (samples: Int16Array) => {
    const node = playbackNodeRef.current;
    if (!node || samples.length === 0) return;
    const copy = samples.buffer.slice(samples.byteOffset, samples.byteOffset + samples.byteLength);
    node.port.postMessage(copy, [copy]);
    metricsRef.current.enqueuedChunks += 1;
    metricsRef.current.totalEnqueuedSamples += samples.length;
  };

  const handleDrawingChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) { setSelectedDrawing(null); return; }
    try {
      const drawing = await readDrawingFile(file);
      setSelectedDrawing(drawing);
      if (actionMessage) setActionMessage("");
      setAppState((cur) => (cur === "error" ? "idle" : cur));
    } catch (error) {
      setSelectedDrawing(null);
      setAppState("error");
      setActionMessage(
        error instanceof Error && error.message === "invalid_image_type"
          ? "Select a valid image file for the drawing."
          : "Could not read the drawing image. Please try again."
      );
    }
  };

  const start = async () => {
    if (appState !== "idle" && appState !== "error") return;

    const consentValidation = validateConsentForStart(caregiverConsent);
    if (!consentValidation.ok) {
      setAppState("error");
      setActionMessage(consentValidation.message);
      return;
    }
    if (!selectedDrawing) {
      setAppState("error");
      setActionMessage("Capture or choose the drawing before starting.");
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
      setActiveSessionId(sessionId);
      writeActiveSessionId(sessionId);

      setAppState("deriving_persona");
      try {
        const personaResult = await derivePersonaFromDrawing({
          sessionId,
          drawingImageBase64: selectedDrawing.imageBase64,
          drawingMimeType: selectedDrawing.mimeType,
          childContext: childName.trim() ? { childName: childName.trim() } : undefined,
          apiBaseUrl,
        });
        setInitialGreeting(personaResult.greetingText);
      } catch {
        setInitialGreeting("Hi, let's play together!");
      }

      const wsUrl = buildLiveWebSocketUrl({ sessionId, apiBaseUrl, wsUrlTemplate });
      setAppState("connecting");

      const captureContext = new AudioContext();
      captureContextRef.current = captureContext;
      await captureContext.resume();

      const playbackContext = new AudioContext({ sampleRate: 24000 });
      playbackContextRef.current = playbackContext;
      await playbackContext.resume();

      await playbackContext.audioWorklet.addModule(
        new URL("../audio/worklets/pcm-playback-worklet.ts", import.meta.url)
      );
      const playbackNode = new AudioWorkletNode(playbackContext, "pcm-playback-worklet");
      playbackNode.connect(playbackContext.destination);
      playbackNodeRef.current = playbackNode;

      playbackNode.port.onmessage = (event: MessageEvent) => {
        const data = event.data as { type?: string } | undefined;
        if (data?.type === "metrics") {
          const m = data as unknown as {
            bufferedSamples: number; underflowFrames: number;
            overflowSamples: number; totalWritten: number; totalRead: number;
          };
          metricsRef.current.workletBufferedSamples = m.bufferedSamples;
          metricsRef.current.workletUnderflowFrames = m.underflowFrames;
          metricsRef.current.workletOverflowSamples = m.overflowSamples;
          metricsRef.current.workletTotalWritten = m.totalWritten;
          metricsRef.current.workletTotalRead = m.totalRead;
        }
      };

      await captureContext.audioWorklet.addModule(
        new URL("../audio/worklets/capture-worklet.ts", import.meta.url)
      );
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const source = captureContext.createMediaStreamSource(stream);
      const captureNode = new AudioWorkletNode(captureContext, "capture-worklet");
      source.connect(captureNode);

      const websocket = new WebSocket(wsUrl);
      websocket.binaryType = "arraybuffer";
      websocketRef.current = websocket;
      downstreamCarryRef.current = new Uint8Array(0);
      let configSent = false;

      captureNode.port.onmessage = (event: MessageEvent) => {
        const data = event.data as { kind: string; sampleRate: number; channels: number; encoding: string; data: ArrayBuffer };
        if (data.kind !== "pcm16" || websocket.readyState !== WebSocket.OPEN) return;
        if (!configSent) {
          websocket.send(JSON.stringify({ type: "audio_config", sample_rate: data.sampleRate, channels: data.channels, encoding: data.encoding }));
          configSent = true;
        }
        websocket.send(data.data);
      };

      websocket.onopen = () => {
        setAppState("ready");
        const setupTimeMs = performance.now() - startTime;
        (window as AppWindow).__animismSetupMetrics = { setupTimeMs };
      };

      websocket.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
        if (typeof event.data === "string") {
          try {
            const parsed = JSON.parse(event.data) as unknown;
            const parsedObj = parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : null;
            if (parsedObj?.type) {
              debugLog({ event_type: "ws_text_received", source: "ChildSessionPage", event_kind: String(parsedObj.type), scene_id: typeof parsedObj.scene_id === "string" ? parsedObj.scene_id : undefined });
            }
            const mediaEvent = parseMediaEvent(parsed);
            if (mediaEvent) {
              debugLog({ event_type: "media_event_dispatched", source: "ChildSessionPage", scene_id: mediaEvent.scene_id, event_kind: mediaEvent.type });
              dispatchMediaEvent(mediaEvent);
              return;
            }
            const chunks = extractPcmAudioChunksFromAdkEvent(parsed);
            for (const chunk of chunks) {
              const { samples, carry } = decodePcm16StreamChunk(chunk.buffer, downstreamCarryRef.current);
              downstreamCarryRef.current = carry;
              if (samples.length > 0) sendSamplesToWorklet(samples);
            }
          } catch { /* ignore */ }
          return;
        }
        const { samples, carry } = decodePcm16StreamChunk(event.data, downstreamCarryRef.current);
        downstreamCarryRef.current = carry;
        if (samples.length > 0) sendSamplesToWorklet(samples);
      };

      websocket.onerror = () => {
        setAppState("error");
        setActionMessage("Real-time connection failed. Please retry.");
      };

      websocket.onclose = () => {
        playbackNodeRef.current?.port.postMessage({ command: "getMetrics" });
        // Abnormal close and manual end can race; close audio contexts idempotently.
        const captureContext = captureContextRef.current;
        captureContextRef.current = null;
        if (captureContext && captureContext.state !== "closed") {
          void captureContext.close().catch(() => {});
        }
        const playbackContext = playbackContextRef.current;
        playbackContextRef.current = null;
        if (playbackContext && playbackContext.state !== "closed") {
          void playbackContext.close().catch(() => {});
        }
        if (timerRef.current) clearInterval(timerRef.current);
        setAppState((prev) => {
          if (prev !== "error" && prev !== "idle") setActionMessage("Session ended. Click Retry to connect again.");
          return "error";
        });
      };
    } catch (error) {
      console.error("Session startup failed.", error);
      setAppState("error");
      setActionMessage("Could not start session. Verify consent and try again.");
    }
  };

  const cleanupLocalResources = () => {
    websocketRef.current?.close();
    const captureContext = captureContextRef.current;
    captureContextRef.current = null;
    if (captureContext && captureContext.state !== "closed") {
      void captureContext.close().catch(() => {});
    }

    const playbackContext = playbackContextRef.current;
    playbackContextRef.current = null;
    if (playbackContext && playbackContext.state !== "closed") {
      void playbackContext.close().catch(() => {});
    }

    setAppState("idle");
    setActionMessage("");
    resetTimeline();
    setSessionDuration(0);
    setActiveSessionId("");
  };

  const endSession = async () => {
    // 1. Explicit sign-off trigger path in live session orchestration
    if (websocketRef.current?.readyState === WebSocket.OPEN) {
      try {
        websocketRef.current.send(JSON.stringify({
          type: "text",
          text: "The session is ending. Please say a brief, warm goodbye."
        }));
      } catch (err) {
        console.warn("Could not send sign-off trigger", err);
      }
    }

    // 2. Attempt graceful backend signoff
    if (activeSessionId) {
      try {
        const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
        await requestSessionEnd(activeSessionId, apiBaseUrl);
      } catch (err) {
        console.warn("Backend session end failed", err);
      }
    }
    
    // 3. Always cleanup local resources
    cleanupLocalResources();
  };

  if (appState === "ready") {
    return (
      <LiveView
        childName={childName}
        selectedDrawing={selectedDrawing}
        initialGreeting={initialGreeting}
        scenes={scenes}
        isMicActive
        sessionDuration={sessionDuration}
        onEndSession={endSession}
      />
    );
  }

  return (
    <SetupView
      childName={childName}
      setChildName={setChildName}
      caregiverConsent={caregiverConsent}
      setCaregiverConsent={setCaregiverConsent}
      selectedDrawing={selectedDrawing}
      onDrawingChange={(e) => void handleDrawingChange(e)}
      onStart={() => void start()}
      appState={appState}
      actionMessage={actionMessage}
    />
  );
}
