/**
 * SceneCard — renders an individual scene within the NarrativeTimeline.
 *
 * Handles all scene status variants:
 * - generating  → sparkle/shimmer placeholder (F3.2)
 * - image_ready → gradient placeholder for mock image
 * - delayed     → Ken Burns on image if available, else delayed placeholder (F3.3)
 * - video_ready → video placeholder with play icon
 *
 * Uses motion.article for enter/exit transitions. Ken Burns itself is
 * pure CSS keyframes (F3.3 AC1: "CSS-only Ken Burns animation utility").
 *
 * @see validation-frontend-epic3-story.md — F3.2, F3.3
 */

import { motion } from "motion/react";
import { memo } from "react";

import type { Scene } from "./mediaEventTypes";

interface SceneCardProps {
  readonly scene: Scene;
}

/** Status labels for accessibility (NFR11). */
const STATUS_LABELS: Record<Scene["status"], string> = {
  generating: "Creating magic...",
  image_ready: "Image ready",
  delayed: "Creating something special...",
  video_ready: "Video ready!",
};

function SceneContent({ scene }: SceneCardProps) {
  switch (scene.status) {
    case "generating":
      return (
        <div
          className="scene-placeholder"
          aria-busy="true"
          aria-label={STATUS_LABELS.generating}
        >
          <div className="scene-sparkle-icon" aria-hidden="true">
            ✨
          </div>
          <span className="scene-placeholder-text">
            {STATUS_LABELS.generating}
          </span>
        </div>
      );

    case "image_ready":
      return (
        <div className="scene-image-container">
          <div
            className="scene-image-placeholder"
            role="img"
            aria-label={`Generated image for ${scene.sceneId}`}
            style={{
              aspectRatio: `${scene.imageWidth ?? 1024} / ${scene.imageHeight ?? 1024}`,
            }}
          />
          <span className="scene-status-badge scene-status-badge--ready">
            {STATUS_LABELS.image_ready}
          </span>
        </div>
      );

    case "delayed":
      return (
        <div className="scene-image-container">
          {scene.imageUrl ? (
            // Ken Burns on existing image (F3.3 AC3)
            <div
              className="scene-image-placeholder scene-ken-burns"
              role="img"
              aria-label={`Image with animation for ${scene.sceneId}`}
              style={{
                aspectRatio: `${scene.imageWidth ?? 1024} / ${scene.imageHeight ?? 1024}`,
              }}
            />
          ) : (
            // No image yet — delayed placeholder
            <div
              className="scene-delayed-placeholder"
              aria-busy="true"
              aria-label={STATUS_LABELS.delayed}
            />
          )}
          <span
            className="scene-status-badge scene-status-badge--delayed"
            aria-live="polite"
          >
            {STATUS_LABELS.delayed}
          </span>
        </div>
      );

    case "video_ready":
      return (
        <div
          className="scene-video-container"
          aria-label={`Video for ${scene.sceneId}`}
        >
          <div className="scene-video-placeholder">
            <span className="scene-video-icon" aria-hidden="true">
              ▶
            </span>
            <span className="scene-video-text">{STATUS_LABELS.video_ready}</span>
            {scene.videoDuration != null && (
              <span className="scene-video-duration">
                {scene.videoDuration}s
              </span>
            )}
          </div>
        </div>
      );
  }
}

function SceneCardInner({ scene }: SceneCardProps) {
  return (
    <motion.article
      className="scene-card"
      data-scene-id={scene.sceneId}
      data-status={scene.status}
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
      layout
    >
      <SceneContent scene={scene} />
    </motion.article>
  );
}

export const SceneCard = memo(SceneCardInner);
