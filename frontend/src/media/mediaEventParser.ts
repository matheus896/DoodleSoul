/**
 * Media event parser — validates and type-narrows incoming WebSocket JSON
 * into typed MediaEvent objects.
 *
 * Design: pure function, zero side effects, easy to unit test.
 * Returns `null` for any payload that isn't a recognised media event,
 * allowing the caller to fall through to audio extraction.
 *
 * ## Observability (Epic 3)
 * ``classifyMediaPayload`` returns explicit drop reasons for diagnostic use.
 * ``parseMediaEvent`` logs drops to ``debugSink`` when ``VITE_DEBUG_MEDIA`` is set.
 *
 * ## Payload compatibility note
 * ``drawing_in_progress`` (direct type) is accepted alongside the pilot-format
 * ``system_instruction`` + ``text: "drawing_in_progress"`` — both are normalised
 * to ``DrawingInProgressEvent``.  See media_orchestrator.py for the emitter.
 *
 * @see mediaEventTypes.ts — type definitions
 * @see validation-frontend-epic3-story.md — F3.1 AC1
 */

import type {
  DrawingInProgressEvent,
  ImageCreatedEvent,
  MediaDelayedEvent,
  MediaEvent,
  VideoCreatedEvent,
} from "./mediaEventTypes";
import { debugLog } from "./debugSink";

// ---------------------------------------------------------------------------
// Recognised type discriminators
// ---------------------------------------------------------------------------

/** Set of recognised `type` discriminators for fast lookup. */
const MEDIA_EVENT_TYPES = new Set([
  "system_instruction",
  "drawing_in_progress", // direct format emitted by MediaOrchestrator — see compat note above
  "media.image.created",
  "media_delayed",
  "media.video.created",
]);

// ---------------------------------------------------------------------------
// Parse diagnostic contract
// ---------------------------------------------------------------------------

/**
 * Diagnostic result from ``classifyMediaPayload``.
 * Provides both the parsed event (or null) and an explicit drop reason
 * for observability tooling.
 */
export interface ParseDiagnostic {
  readonly event: MediaEvent | null;
  /** Human-readable reason for the drop, or null when event is valid. */
  readonly dropReason: string | null;
}

/** Drop reason constants for type-safe diagnostic assertions in tests. */
export const DROP_REASON = {
  NOT_AN_OBJECT: "not_an_object",
  NO_TYPE_FIELD: "no_type_field",
  UNKNOWN_EVENT_TYPE: "unknown_event_type",
  MISSING_SCENE_ID: "missing_scene_id",
  IMAGE_MISSING_URL: "image_missing_url",
  IMAGE_MISSING_DIMENSIONS: "image_missing_dimensions",
  DELAYED_MISSING_ELAPSED: "delayed_missing_elapsed",
  VIDEO_MISSING_URL: "video_missing_url",
  VIDEO_MISSING_DURATION: "video_missing_duration",
  INSTRUCTION_WRONG_TEXT: "instruction_wrong_text",
} as const;

// ---------------------------------------------------------------------------
// classifyMediaPayload — explicit diagnostic classification
// ---------------------------------------------------------------------------

/**
 * Classify an unknown payload and return both the typed event and a drop reason.
 *
 * This is the single authoritative classification function; ``parseMediaEvent``
 * delegates to it and adds debug-sink logging.
 */
export function classifyMediaPayload(data: unknown): ParseDiagnostic {
  if (!data || typeof data !== "object") {
    return { event: null, dropReason: DROP_REASON.NOT_AN_OBJECT };
  }

  const obj = data as Record<string, unknown>;
  const type = obj.type;

  if (typeof type !== "string") {
    return { event: null, dropReason: DROP_REASON.NO_TYPE_FIELD };
  }

  if (!MEDIA_EVENT_TYPES.has(type)) {
    return { event: null, dropReason: DROP_REASON.UNKNOWN_EVENT_TYPE };
  }

  // All recognised media events require scene_id
  if (typeof obj.scene_id !== "string" || obj.scene_id.length === 0) {
    return { event: null, dropReason: DROP_REASON.MISSING_SCENE_ID };
  }

  switch (type) {
    case "system_instruction": {
      if (obj.text !== "drawing_in_progress") {
        return { event: null, dropReason: DROP_REASON.INSTRUCTION_WRONG_TEXT };
      }
      return { event: obj as unknown as DrawingInProgressEvent, dropReason: null };
    }

    case "drawing_in_progress": {
      // Normalise direct format (MediaOrchestrator) to DrawingInProgressEvent
      const normalised: DrawingInProgressEvent = {
        type: "system_instruction",
        text: "drawing_in_progress",
        scene_id: obj.scene_id as string,
      };
      return { event: normalised, dropReason: null };
    }

    case "media.image.created": {
      if (typeof obj.url !== "string") {
        return { event: null, dropReason: DROP_REASON.IMAGE_MISSING_URL };
      }
      if (typeof obj.width !== "number" || typeof obj.height !== "number") {
        return { event: null, dropReason: DROP_REASON.IMAGE_MISSING_DIMENSIONS };
      }
      return { event: obj as unknown as ImageCreatedEvent, dropReason: null };
    }

    case "media_delayed": {
      if (typeof obj.elapsed_seconds !== "number") {
        return { event: null, dropReason: DROP_REASON.DELAYED_MISSING_ELAPSED };
      }
      return { event: obj as unknown as MediaDelayedEvent, dropReason: null };
    }

    case "media.video.created": {
      if (typeof obj.url !== "string") {
        return { event: null, dropReason: DROP_REASON.VIDEO_MISSING_URL };
      }
      if (typeof obj.duration_seconds !== "number") {
        return { event: null, dropReason: DROP_REASON.VIDEO_MISSING_DURATION };
      }
      return { event: obj as unknown as VideoCreatedEvent, dropReason: null };
    }

    default:
      return { event: null, dropReason: DROP_REASON.UNKNOWN_EVENT_TYPE };
  }
}

// ---------------------------------------------------------------------------
// parseMediaEvent — public API (backward-compatible, adds debug logging)
// ---------------------------------------------------------------------------

/**
 * Attempt to parse an unknown JSON payload as a MediaEvent.
 *
 * @returns The typed event if valid, or `null` if the payload is not a
 *          recognised media event (allowing fallthrough to audio logic).
 *
 * When ``VITE_DEBUG_MEDIA`` is set, drops are logged to the debug sink
 * with the explicit reason (except generic non-object payloads which would
 * be too noisy from binary audio frames).
 */
export function parseMediaEvent(data: unknown): MediaEvent | null {
  const { event, dropReason } = classifyMediaPayload(data);

  // Log informative drops (skip binary/non-object noise)
  if (event === null && dropReason !== DROP_REASON.NOT_AN_OBJECT) {
    const obj = data && typeof data === "object"
      ? (data as Record<string, unknown>)
      : null;
    debugLog({
      event_type: "media_event_dropped",
      source: "parser",
      scene_id: typeof obj?.scene_id === "string" ? obj.scene_id : undefined,
      drop_reason: dropReason ?? "unknown",
      event_kind: typeof obj?.type === "string" ? obj.type : undefined,
    });
  }

  return event;
}
