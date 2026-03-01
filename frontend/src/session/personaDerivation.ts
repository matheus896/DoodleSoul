interface DerivePersonaApiSuccess {
  status: "ok";
  data: {
    session_id: string;
    persona_source: string;
    fallback_applied: boolean;
    fallback_reason?: string | null;
    voice_traits: string[];
    personality_traits: string[];
    greeting_text: string;
  };
}

interface DerivePersonaApiError {
  status: "error";
  error: {
    code: string;
    message: string;
  };
}

export interface PersonaDerivationResult {
  sessionId: string;
  personaSource: string;
  fallbackApplied: boolean;
  fallbackReason?: string;
  voiceTraits: string[];
  personalityTraits: string[];
  greetingText: string;
}

interface DerivePersonaParams {
  sessionId: string;
  drawingImageBase64: string;
  drawingMimeType: string;
  childContext?: {
    childName?: string;
  };
  apiBaseUrl?: string;
  fetchImpl?: typeof fetch;
}

export async function derivePersonaFromDrawing(
  params: DerivePersonaParams
): Promise<PersonaDerivationResult> {
  const fetchFn = params.fetchImpl ?? fetch;
  const base = (params.apiBaseUrl ?? "").replace(/\/+$/, "");
  const endpoint = `${base}/api/session/${params.sessionId}/persona/derive`;

  const response = await fetchFn(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({
      drawing_image_base64: params.drawingImageBase64,
      drawing_mime_type: params.drawingMimeType,
      child_context: params.childContext
        ? { child_name: params.childContext.childName }
        : undefined,
    }),
  });

  const payload = (await response.json()) as
    | DerivePersonaApiSuccess
    | DerivePersonaApiError;

  if (!response.ok || payload.status !== "ok") {
    const message =
      "error" in payload && payload.error.message
        ? payload.error.message
        : "Falha ao derivar persona.";
    throw new Error(message);
  }

  return {
    sessionId: payload.data.session_id,
    personaSource: payload.data.persona_source,
    fallbackApplied: payload.data.fallback_applied,
    fallbackReason: payload.data.fallback_reason ?? undefined,
    voiceTraits: payload.data.voice_traits,
    personalityTraits: payload.data.personality_traits,
    greetingText: payload.data.greeting_text,
  };
}
