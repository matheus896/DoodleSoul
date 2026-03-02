/**
 * Media event types emitted by the backend bridge.
 *
 * Contract: PilotMockGeminiLiveStream sends these JSON events through the
 * real WebSocket bridge. Each event has a `type` discriminator and a
 * `scene_id` linking it to a narrative scene.
 *
 * @see backend/app/services/live_client_factory.py — PilotMockGeminiLiveStream
 * @see validation-integration-mocked-story.md — I3.1, I3.2, I3.3
 */

// ---------------------------------------------------------------------------
// Inbound media events (from bridge → frontend)
// ---------------------------------------------------------------------------

export interface DrawingInProgressEvent {
  readonly type: "system_instruction";
  readonly text: "drawing_in_progress";
  readonly scene_id: string;
}

export interface ImageCreatedEvent {
  readonly type: "media.image.created";
  readonly scene_id: string;
  readonly media_type: "image";
  readonly url: string;
  readonly width: number;
  readonly height: number;
  readonly payload_size_bytes: number;
}

export interface MediaDelayedEvent {
  readonly type: "media_delayed";
  readonly scene_id: string;
  readonly elapsed_seconds: number;
}

export interface VideoCreatedEvent {
  readonly type: "media.video.created";
  readonly scene_id: string;
  readonly media_type: "video";
  readonly url: string;
  readonly duration_seconds: number;
  readonly payload_size_bytes: number;
}

/** Discriminated union of all recognised media events. */
export type MediaEvent =
  | DrawingInProgressEvent
  | ImageCreatedEvent
  | MediaDelayedEvent
  | VideoCreatedEvent;

// ---------------------------------------------------------------------------
// Scene state model (frontend-only)
// ---------------------------------------------------------------------------

/**
 * Lifecycle status of a single narrative scene.
 *
 * Transitions:
 *   generating ──→ image_ready ──→ delayed ──→ video_ready
 *                                  │              ▲
 *                                  └──────────────┘
 *
 * A scene may skip intermediate states (e.g. jump from generating to delayed
 * if no image arrives first).
 */
export type SceneStatus = "generating" | "image_ready" | "delayed" | "video_ready";

/** Represents a single scene in the narrative timeline. */
export interface Scene {
  readonly sceneId: string;
  readonly status: SceneStatus;
  readonly imageUrl: string | null;
  readonly videoUrl: string | null;
  readonly imageWidth: number | null;
  readonly imageHeight: number | null;
  readonly videoDuration: number | null;
  /** True when Ken Burns fallback should be active (F3.3). */
  readonly fallbackActive: boolean;
  readonly createdAt: number;
  readonly updatedAt: number;
}
