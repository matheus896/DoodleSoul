/**
 * useLiveInsights — polls GET /api/dashboard/insights/{session_id} every 3s.
 * Returns alerts array and connection status. No external deps required.
 */

import { useEffect, useRef, useState } from "react";

export interface ClinicalAlert {
  primary_emotion: string;
  trigger: string;
  risk_level: "low" | "medium" | "high" | string;
  recommended_strategy: string;
  child_quote_summary: string;
}

interface InsightsData {
  session_id: string;
  child_name?: string;
  session_start_time?: string;
  is_closed?: boolean;
  ended_at?: string | null;
  alerts: ClinicalAlert[];
  emotional_state_current?: string;
}

interface InsightsResponse {
  status: "ok" | "error";
  data: InsightsData;
}

export type InsightsStatus = "idle" | "loading" | "ok" | "error";

interface UseLiveInsightsReturn {
  alerts: ClinicalAlert[];
  status: InsightsStatus;
  errorMessage: string | null;
  lastUpdated: Date | null;
  childName?: string;
  sessionStartTime?: Date | null;
  isClosed: boolean;
  endedAt: Date | null;
  emotionalStateCurrent?: string;
}

const POLL_INTERVAL_MS = 3000;

export function useLiveInsights(
  sessionId: string | null,
  apiBaseUrl?: string
): UseLiveInsightsReturn {
  const [alerts, setAlerts] = useState<ClinicalAlert[]>([]);
  const [status, setStatus] = useState<InsightsStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [childName, setChildName] = useState<string | undefined>(undefined);
  const [sessionStartTime, setSessionStartTime] = useState<Date | null>(null);
  const [isClosed, setIsClosed] = useState(false);
  const [endedAt, setEndedAt] = useState<Date | null>(null);
  const [emotionalStateCurrent, setEmotionalStateCurrent] = useState<string | undefined>(undefined);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setStatus("idle");
      return;
    }

    const base = (apiBaseUrl ?? "").replace(/\/+$/, "");
    const endpoint = `${base}/api/dashboard/insights/${sessionId}`;

    const fetchInsights = async () => {
      try {
        const response = await fetch(endpoint);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const payload = (await response.json()) as InsightsResponse;
        if (payload.status === "ok") {
          setAlerts(payload.data.alerts ?? []);
          setStatus("ok");
          setErrorMessage(null);
          setLastUpdated(new Date());
          if (payload.data.child_name) {
            setChildName(payload.data.child_name);
          }
          if (payload.data.session_start_time) {
            setSessionStartTime(new Date(payload.data.session_start_time));
          }
          const closed = payload.data.is_closed === true;
          setIsClosed(closed);
          setEndedAt(payload.data.ended_at ? new Date(payload.data.ended_at) : null);
          if (payload.data.emotional_state_current) {
            setEmotionalStateCurrent(payload.data.emotional_state_current);
          }
          // Stop polling once backend confirms session is closed — no further state changes expected.
          if (closed && intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        } else {
          setStatus("error");
          setErrorMessage("Unexpected response from server.");
        }
      } catch (err) {
        setStatus("error");
        setErrorMessage(err instanceof Error ? err.message : "Unknown error");
      }
    };

    // Initial fetch
    setStatus("loading");
    void fetchInsights();

    // Polling
    intervalRef.current = setInterval(() => void fetchInsights(), POLL_INTERVAL_MS);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [sessionId, apiBaseUrl]);

  return {
    alerts,
    status,
    errorMessage,
    lastUpdated,
    childName,
    sessionStartTime,
    isClosed,
    endedAt,
    emotionalStateCurrent,
  };
}
