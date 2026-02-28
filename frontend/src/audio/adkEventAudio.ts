export interface PcmAudioChunk {
  buffer: ArrayBuffer;
  sampleRate: number | null;
}

function decodeBase64ToArrayBuffer(encoded: string): ArrayBuffer {
  let normalized = encoded.replace(/-/g, "+").replace(/_/g, "/");
  while (normalized.length % 4 !== 0) {
    normalized += "=";
  }

  const binary = window.atob(normalized);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function parsePcmRate(mimeType: string): number | null {
  const match = mimeType.match(/rate=(\d+)/i);
  if (!match) {
    return null;
  }
  const parsed = Number.parseInt(match[1] ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function extractPcmAudioChunksFromAdkEvent(payload: unknown): PcmAudioChunk[] {
  if (!payload || typeof payload !== "object") {
    return [];
  }

  const event = payload as {
    content?: { parts?: Array<Record<string, unknown>> };
  };

  const parts = event.content?.parts;
  if (!Array.isArray(parts)) {
    return [];
  }

  const chunks: PcmAudioChunk[] = [];
  for (const part of parts) {
    if (!part || typeof part !== "object") {
      continue;
    }
    const inlineData = (part.inlineData ?? part.inline_data) as
      | { mimeType?: string; mime_type?: string; data?: string }
      | undefined;
    if (!inlineData || typeof inlineData !== "object") {
      continue;
    }

    const mimeType = inlineData.mimeType ?? inlineData.mime_type ?? "";
    if (!mimeType.startsWith("audio/pcm")) {
      continue;
    }
    if (typeof inlineData.data !== "string" || inlineData.data.length === 0) {
      continue;
    }

    chunks.push({
      buffer: decodeBase64ToArrayBuffer(inlineData.data),
      sampleRate: parsePcmRate(mimeType),
    });
  }
  return chunks;
}
