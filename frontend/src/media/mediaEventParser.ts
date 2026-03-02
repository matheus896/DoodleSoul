/**
 * Media event parser — validates and type-narrows incoming WebSocket JSON
 * into typed MediaEvent objects.
 *
 * Design: pure function, zero side effects, easy to unit test.
 * Returns `null` for any payload that isn't a recognised media event,
 * allowing the caller to fall through to audio extraction.
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

/** Set of recognised `type` discriminators for fast lookup. */
const MEDIA_EVENT_TYPES = new Set([
  "system_instruction",
  "media.image.created",
  "media_delayed",
  "media.video.created",
]);

/**
 * Attempt to parse an unknown JSON payload as a MediaEvent.
 *
 * @returns The typed event if valid, or `null` if the payload is not a
 *          recognised media event (allowing fallthrough to audio logic).
 */
export function parseMediaEvent(data: unknown): MediaEvent | null {
  if (!data || typeof data !== "object") {
    return null;
  }

  const obj = data as Record<string, unknown>;
  const type = obj.type;

  if (typeof type !== "string" || !MEDIA_EVENT_TYPES.has(type)) {
    return null;
  }

  // All media events require scene_id
  if (typeof obj.scene_id !== "string" || obj.scene_id.length === 0) {
    return null;
  }

  switch (type) {
    case "system_instruction": {
      if (obj.text !== "drawing_in_progress") {
        return null;
      }
      return obj as unknown as DrawingInProgressEvent;
    }

    case "media.image.created": {
      if (
        typeof obj.url !== "string" ||
        typeof obj.width !== "number" ||
        typeof obj.height !== "number"
      ) {
        return null;
      }
      return obj as unknown as ImageCreatedEvent;
    }

    case "media_delayed": {
      if (typeof obj.elapsed_seconds !== "number") {
        return null;
      }
      return obj as unknown as MediaDelayedEvent;
    }

    case "media.video.created": {
      if (
        typeof obj.url !== "string" ||
        typeof obj.duration_seconds !== "number"
      ) {
        return null;
      }
      return obj as unknown as VideoCreatedEvent;
    }

    default:
      return null;
  }
}
