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
  alerts: ClinicalAlert[];
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

  return { alerts, status, errorMessage, lastUpdated };
}
