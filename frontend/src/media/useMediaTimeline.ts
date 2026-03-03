/**
 * useMediaTimeline — React hook managing narrative timeline state.
 *
 * Architecture:
 * - Reducer-based (pure function, directly testable without React).
 * - Stable `dispatchMediaEvent` callback (safe for WS onmessage closures).
 * - Ordered scenes array via useMemo (avoids re-computation on unrelated renders).
 * - Scene state isolated per scene_id (F3.3 AC3: fallback_active is scene-scoped).
 *
 * @see mediaEventTypes.ts — Scene, MediaEvent types
 * @see validation-frontend-epic3-story.md — F3.1, F3.3
 */

import { useCallback, useMemo, useReducer } from "react";

import type { MediaEvent, Scene, SceneStatus } from "./mediaEventTypes";
import { debugLog } from "./debugSink";

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

export interface TimelineState {
  /** Scene data keyed by scene_id. */
  readonly scenes: Readonly<Record<string, Scene>>;
  /** Ordered list of scene_ids (insertion order). */
  readonly sceneOrder: readonly string[];
}

export type TimelineAction =
  | { readonly type: "MEDIA_EVENT"; readonly event: MediaEvent }
  | { readonly type: "RESET" };

const INITIAL_STATE: TimelineState = {
  scenes: {},
  sceneOrder: [],
};

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function createScene(sceneId: string, status: SceneStatus, now: number): Scene {
  return {
    sceneId,
    status,
    imageUrl: null,
    videoUrl: null,
    imageWidth: null,
    imageHeight: null,
    videoDuration: null,
    fallbackActive: false,
    createdAt: now,
    updatedAt: now,
  };
}

function applyMediaEvent(state: TimelineState, event: MediaEvent): TimelineState {
  const now = Date.now();
  const sceneId = event.scene_id;
  const existing = state.scenes[sceneId] as Scene | undefined;

  const newScenes = { ...state.scenes };
  let newOrder = state.sceneOrder;

  // Ensure scene order includes this scene_id
  if (!existing) {
    newOrder = [...state.sceneOrder, sceneId];
  }

  switch (event.type) {
    case "system_instruction": {
      // drawing_in_progress — create scene in "generating" status
      if (!existing) {
        newScenes[sceneId] = createScene(sceneId, "generating", now);
      }
      // If scene already exists, don't regress its status
      break;
    }

    case "media.image.created": {
      const base = existing ?? createScene(sceneId, "generating", now);
      newScenes[sceneId] = {
        ...base,
        status: "image_ready",
        imageUrl: event.url,
        imageWidth: event.width,
        imageHeight: event.height,
        fallbackActive: false,
        updatedAt: now,
      };
      break;
    }

    case "media_delayed": {
      const base = existing ?? createScene(sceneId, "generating", now);
      newScenes[sceneId] = {
        ...base,
        status: "delayed",
        fallbackActive: true,
        updatedAt: now,
      };
      break;
    }

    case "media.video.created": {
      const base = existing ?? createScene(sceneId, "generating", now);
      newScenes[sceneId] = {
        ...base,
        status: "video_ready",
        videoUrl: event.url,
        videoDuration: event.duration_seconds,
        fallbackActive: false,
        updatedAt: now,
      };
      break;
    }
  }

  return { scenes: newScenes, sceneOrder: newOrder };
}

// ---------------------------------------------------------------------------
// Reducer (exported for direct unit testing)
// ---------------------------------------------------------------------------

export function timelineReducer(
  state: TimelineState,
  action: TimelineAction,
): TimelineState {
  switch (action.type) {
    case "MEDIA_EVENT":
      return applyMediaEvent(state, action.event);
    case "RESET":
      return INITIAL_STATE;
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseMediaTimelineResult {
  /** Ordered array of scenes for rendering. */
  readonly scenes: readonly Scene[];
  /** Dispatch a media event to update timeline state. Stable reference. */
  readonly dispatchMediaEvent: (event: MediaEvent) => void;
  /** Reset timeline to empty state (on new session start). Stable reference. */
  readonly reset: () => void;
}

export function useMediaTimeline(): UseMediaTimelineResult {
  const [state, dispatch] = useReducer(timelineReducer, INITIAL_STATE);

  const dispatchMediaEvent = useCallback(
    (event: MediaEvent) => {
      debugLog({
        event_type: "timeline_event_dispatched",
        source: "useMediaTimeline",
        scene_id: event.scene_id,
        event_kind: event.type,
      });
      dispatch({ type: "MEDIA_EVENT", event });
    },
    [],
  );

  const reset = useCallback(() => {
    dispatch({ type: "RESET" });
  }, []);

  const scenes = useMemo(
    () =>
      state.sceneOrder
        .map((id) => state.scenes[id])
        .filter((s): s is Scene => s != null),
    [state.scenes, state.sceneOrder],
  );

  return { scenes, dispatchMediaEvent, reset };
}
