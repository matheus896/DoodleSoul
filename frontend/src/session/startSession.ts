export type ConsentValidationResult =
  | { ok: true }
  | { ok: false; message: string };

interface BuildLiveWebSocketUrlParams {
  sessionId: string;
  apiBaseUrl?: string;
  wsUrlTemplate?: string;
}

interface StartSessionRequest {
  caregiver_consent: boolean;
}

interface StartSessionSuccess {
  status: "ok";
  data: {
    session_id: string;
    consent_captured: boolean;
    consent_captured_at: string;
  };
}

interface StartSessionError {
  status: "error";
  error: {
    code: string;
    message: string;
  };
}

export function validateConsentForStart(
  caregiverConsent: boolean
): ConsentValidationResult {
  if (!caregiverConsent) {
    return {
      ok: false,
      message: "Please confirm consent before starting the session.",
    };
  }
  return { ok: true };
}

export function buildLiveWebSocketUrl({
  sessionId,
  apiBaseUrl,
  wsUrlTemplate,
}: BuildLiveWebSocketUrlParams): string {
  if (wsUrlTemplate) {
    const normalizedTemplate = wsUrlTemplate.replace(/\/+$/, "");
    if (normalizedTemplate.includes("{session_id}")) {
      return normalizedTemplate.replace("{session_id}", sessionId);
    }

    const livePathMatch = normalizedTemplate.match(/^(.*\/ws\/live)\/[^/]+$/);
    if (livePathMatch) {
      return `${livePathMatch[1]}/${sessionId}`;
    }

    const wsBase = normalizedTemplate.replace(/^http/i, "ws");
    return `${wsBase}/ws/live/${sessionId}`;
  }

  const base = (apiBaseUrl ?? window.location.origin).replace(/\/+$/, "");
  const wsBase = base.replace(/^http/i, "ws");
  return `${wsBase}/ws/live/${sessionId}`;
}

export async function requestSessionStart(apiBaseUrl?: string): Promise<string> {
  const base = (apiBaseUrl ?? "").replace(/\/+$/, "");
  const endpoint = `${base}/api/session/start`;
  const requestBody: StartSessionRequest = { caregiver_consent: true };

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  const payload = (await response.json()) as StartSessionSuccess | StartSessionError;

  if (!response.ok || payload.status !== "ok") {
    const message =
      "error" in payload && payload.error.message
        ? payload.error.message
        : "Failed to start session.";
    throw new Error(message);
  }

  return payload.data.session_id;
}

export async function requestSessionEnd(sessionId: string, apiBaseUrl?: string): Promise<void> {
  const base = (apiBaseUrl ?? "").replace(/\/+$/, "");
  const endpoint = `${base}/api/session/${sessionId}/end`;

  await fetch(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
  });
}
