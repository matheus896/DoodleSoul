/**
 * Tests for timelineReducer — validates scene state transitions.
 *
 * Tests the reducer as a pure function (no React hooks needed).
 * Covers: scene creation, status transitions, fallback isolation (F3.3 AC3),
 * out-of-order events (I3.3), and idempotency.
 *
 * @see validation-frontend-epic3-story.md — F3.1, F3.3
 * @see validation-integration-mocked-story.md — I3.3
 */

import { describe, expect, it } from "vitest";

import type { MediaEvent, Scene } from "../mediaEventTypes";
import {
  type TimelineState,
  timelineReducer,
} from "../useMediaTimeline";

// ── Helper: create events matching the pilot mock contract ──

function drawingInProgress(sceneId: string): MediaEvent {
  return { type: "system_instruction", text: "drawing_in_progress", scene_id: sceneId };
}

function imageCreated(sceneId: string): MediaEvent {
  return {
    type: "media.image.created",
    scene_id: sceneId,
    media_type: "image",
    url: `mock://imagen/${sceneId}.png`,
    width: 1024,
    height: 1024,
    payload_size_bytes: 51200,
  };
}

function mediaDelayed(sceneId: string, elapsed = 30): MediaEvent {
  return { type: "media_delayed", scene_id: sceneId, elapsed_seconds: elapsed };
}

function videoCreated(sceneId: string): MediaEvent {
  return {
    type: "media.video.created",
    scene_id: sceneId,
    media_type: "video",
    url: `mock://veo/${sceneId}.mp4`,
    duration_seconds: 8,
    payload_size_bytes: 102400,
  };
}

function dispatch(state: TimelineState, event: MediaEvent): TimelineState {
  return timelineReducer(state, { type: "MEDIA_EVENT", event });
}

const EMPTY: TimelineState = { scenes: {}, sceneOrder: [] };

function getScene(state: TimelineState, id: string): Scene | undefined {
  return state.scenes[id];
}

// ── Tests ──

describe("timelineReducer", () => {
  describe("scene creation", () => {
    it("creates a scene on drawing_in_progress", () => {
      const s = dispatch(EMPTY, drawingInProgress("scene-1"));
      expect(s.sceneOrder).toEqual(["scene-1"]);
      const scene = getScene(s, "scene-1")!;
      expect(scene.status).toBe("generating");
      expect(scene.fallbackActive).toBe(false);
      expect(scene.imageUrl).toBeNull();
      expect(scene.videoUrl).toBeNull();
    });

    it("creates a scene on image_created if not yet seen", () => {
      const s = dispatch(EMPTY, imageCreated("scene-x"));
      expect(s.sceneOrder).toEqual(["scene-x"]);
      expect(getScene(s, "scene-x")!.status).toBe("image_ready");
      expect(getScene(s, "scene-x")!.imageUrl).toBe("mock://imagen/scene-x.png");
    });

    it("creates a scene on media_delayed if not yet seen", () => {
      const s = dispatch(EMPTY, mediaDelayed("scene-2"));
      expect(s.sceneOrder).toEqual(["scene-2"]);
      expect(getScene(s, "scene-2")!.status).toBe("delayed");
      expect(getScene(s, "scene-2")!.fallbackActive).toBe(true);
    });

    it("creates a scene on video_created if not yet seen", () => {
      const s = dispatch(EMPTY, videoCreated("scene-2"));
      expect(s.sceneOrder).toEqual(["scene-2"]);
      expect(getScene(s, "scene-2")!.status).toBe("video_ready");
    });
  });

  describe("status transitions (pilot mock sequence)", () => {
    it("generating → image_ready", () => {
      let s = dispatch(EMPTY, drawingInProgress("scene-1"));
      s = dispatch(s, imageCreated("scene-1"));
      expect(getScene(s, "scene-1")!.status).toBe("image_ready");
      expect(getScene(s, "scene-1")!.imageUrl).toBe("mock://imagen/scene-1.png");
      expect(getScene(s, "scene-1")!.imageWidth).toBe(1024);
    });

    it("image_ready → delayed (Ken Burns activates)", () => {
      let s = dispatch(EMPTY, drawingInProgress("scene-1"));
      s = dispatch(s, imageCreated("scene-1"));
      s = dispatch(s, mediaDelayed("scene-1"));
      const scene = getScene(s, "scene-1")!;
      expect(scene.status).toBe("delayed");
      expect(scene.fallbackActive).toBe(true);
      expect(scene.imageUrl).toBe("mock://imagen/scene-1.png"); // preserved
    });

    it("delayed → video_ready (Ken Burns deactivates)", () => {
      let s = dispatch(EMPTY, drawingInProgress("scene-1"));
      s = dispatch(s, imageCreated("scene-1"));
      s = dispatch(s, mediaDelayed("scene-1"));
      s = dispatch(s, videoCreated("scene-1"));
      const scene = getScene(s, "scene-1")!;
      expect(scene.status).toBe("video_ready");
      expect(scene.fallbackActive).toBe(false);
      expect(scene.videoUrl).toBe("mock://veo/scene-1.mp4");
      expect(scene.imageUrl).toBe("mock://imagen/scene-1.png"); // preserved
    });
  });

  describe("multi-scene isolation (F3.3 AC3, I3.3)", () => {
    it("fallback_active is isolated per scene", () => {
      let s = dispatch(EMPTY, drawingInProgress("scene-1"));
      s = dispatch(s, imageCreated("scene-1"));
      s = dispatch(s, mediaDelayed("scene-2")); // different scene

      expect(getScene(s, "scene-1")!.fallbackActive).toBe(false);
      expect(getScene(s, "scene-2")!.fallbackActive).toBe(true);
    });

    it("preserves scene order across multiple scenes", () => {
      let s = dispatch(EMPTY, drawingInProgress("scene-1"));
      s = dispatch(s, mediaDelayed("scene-2"));
      s = dispatch(s, drawingInProgress("scene-3"));

      expect(s.sceneOrder).toEqual(["scene-1", "scene-2", "scene-3"]);
    });

    it("does not duplicate scene in order on second event", () => {
      let s = dispatch(EMPTY, drawingInProgress("scene-1"));
      s = dispatch(s, imageCreated("scene-1")); // second event, same scene

      expect(s.sceneOrder).toEqual(["scene-1"]);
    });

    it("video_ready on one scene doesn't affect another's delayed status", () => {
      let s = dispatch(EMPTY, drawingInProgress("scene-1"));
      s = dispatch(s, imageCreated("scene-1"));
      s = dispatch(s, mediaDelayed("scene-2"));
      s = dispatch(s, videoCreated("scene-1"));

      expect(getScene(s, "scene-1")!.status).toBe("video_ready");
      expect(getScene(s, "scene-1")!.fallbackActive).toBe(false);
      expect(getScene(s, "scene-2")!.status).toBe("delayed");
      expect(getScene(s, "scene-2")!.fallbackActive).toBe(true);
    });
  });

  describe("pilot mock full sequence", () => {
    it("reproduces the pilot mock event sequence correctly", () => {
      let s = EMPTY;

      // Phase 1: drawing_in_progress for scene-1
      s = dispatch(s, drawingInProgress("scene-1"));
      expect(getScene(s, "scene-1")!.status).toBe("generating");

      // Phase 2: image ready for scene-1
      s = dispatch(s, imageCreated("scene-1"));
      expect(getScene(s, "scene-1")!.status).toBe("image_ready");

      // Phase 3: media_delayed for scene-2 (different scene!)
      s = dispatch(s, mediaDelayed("scene-2"));
      expect(getScene(s, "scene-2")!.status).toBe("delayed");
      expect(getScene(s, "scene-2")!.fallbackActive).toBe(true);
      // scene-1 unaffected
      expect(getScene(s, "scene-1")!.status).toBe("image_ready");

      // Phase 4: video ready for scene-2
      s = dispatch(s, videoCreated("scene-2"));
      expect(getScene(s, "scene-2")!.status).toBe("video_ready");
      expect(getScene(s, "scene-2")!.fallbackActive).toBe(false);

      // Final state
      expect(s.sceneOrder).toEqual(["scene-1", "scene-2"]);
    });
  });

  describe("idempotency", () => {
    it("duplicate drawing_in_progress does not regress status", () => {
      let s = dispatch(EMPTY, drawingInProgress("scene-1"));
      s = dispatch(s, imageCreated("scene-1"));
      s = dispatch(s, drawingInProgress("scene-1")); // duplicate

      // Status should NOT regress to "generating"
      expect(getScene(s, "scene-1")!.status).toBe("image_ready");
    });
  });

  describe("RESET action", () => {
    it("clears all scenes", () => {
      let s = dispatch(EMPTY, drawingInProgress("scene-1"));
      s = dispatch(s, imageCreated("scene-1"));

      const reset = timelineReducer(s, { type: "RESET" });
      expect(reset.scenes).toEqual({});
      expect(reset.sceneOrder).toEqual([]);
    });
  });
});
