/**
 * NarrativeTimeline — renders the ordered sequence of narrative scenes.
 *
 * Architecture:
 * - Memoized to prevent re-renders when parent App state changes (F3.1 AC3).
 * - AnimatePresence handles scene enter/exit transitions.
 * - Each SceneCard is independently memoized and keyed by scene_id.
 * - This component tree is completely isolated from the audio pipeline refs,
 *   ensuring pcmPlayer buffer stability during media reconciliation (F3.1 AC2).
 *
 * @see validation-frontend-epic3-story.md — F3.1
 */

import { AnimatePresence } from "motion/react";
import { memo, useEffect } from "react";

import type { Scene } from "./mediaEventTypes";
import { debugLog } from "./debugSink";
import { SceneCard } from "./SceneCard";

interface NarrativeTimelineProps {
  readonly scenes: readonly Scene[];
}

function NarrativeTimelineInner({ scenes }: NarrativeTimelineProps) {
  // Debug: log scene status transitions for observability (no-op when toggle off)
  useEffect(() => {
    for (const scene of scenes) {
      debugLog({
        event_type: "scene_render",
        source: "NarrativeTimeline",
        scene_id: scene.sceneId,
        status: scene.status,
        has_image: scene.imageUrl !== null,
        has_video: scene.videoUrl !== null,
      });
    }
  }, [scenes]);

  if (scenes.length === 0) {
    return null;
  }

  return (
    <section
      className="narrative-timeline"
      aria-label="Story Timeline"
      role="feed"
      aria-busy={scenes.some((s) => s.status === "generating" || s.status === "delayed")}
    >
      <h2 className="timeline-title">Your Story</h2>
      <AnimatePresence mode="popLayout">
        {scenes.map((scene) => (
          <SceneCard key={scene.sceneId} scene={scene} />
        ))}
      </AnimatePresence>
    </section>
  );
}

export const NarrativeTimeline = memo(NarrativeTimelineInner);
