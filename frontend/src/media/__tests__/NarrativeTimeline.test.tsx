/**
 * Tests for NarrativeTimeline + SceneCard components.
 *
 * Uses renderToString (existing test pattern — no @testing-library/react needed).
 * Validates HTML output, accessibility attributes, and status-dependent rendering.
 *
 * @see validation-frontend-epic3-story.md — F3.1, F3.2, F3.3
 */

import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Scene } from "../mediaEventTypes";
import { NarrativeTimeline } from "../NarrativeTimeline";

// ── Helper: create scene objects ──

function makeScene(overrides: Partial<Scene> & { sceneId: string }): Scene {
  return {
    status: "generating",
    imageUrl: null,
    videoUrl: null,
    imageWidth: null,
    imageHeight: null,
    videoDuration: null,
    fallbackActive: false,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    ...overrides,
  };
}

describe("NarrativeTimeline", () => {
  it("renders nothing when scenes array is empty", () => {
    const html = renderToString(<NarrativeTimeline scenes={[]} />);
    expect(html).toBe("");
  });

  it("renders timeline section with aria-label", () => {
    const scenes = [makeScene({ sceneId: "scene-1" })];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('aria-label="Story Timeline"');
    expect(html).toContain('role="feed"');
    expect(html).toContain("Your Story");
  });

  it("renders aria-busy when any scene is generating", () => {
    const scenes = [makeScene({ sceneId: "scene-1", status: "generating" })];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('aria-busy="true"');
  });

  it("renders multiple scene cards", () => {
    const scenes = [
      makeScene({ sceneId: "scene-1", status: "image_ready" }),
      makeScene({ sceneId: "scene-2", status: "delayed", fallbackActive: true }),
    ];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('data-scene-id="scene-1"');
    expect(html).toContain('data-scene-id="scene-2"');
  });
});

describe("SceneCard rendering by status", () => {
  it("generating: shows sparkle placeholder with aria-busy", () => {
    const scenes = [makeScene({ sceneId: "s1", status: "generating" })];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('data-status="generating"');
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("Creating magic...");
    expect(html).toContain("scene-placeholder");
    expect(html).toContain("✨");
  });

  it("image_ready: shows image placeholder with role=img", () => {
    const scenes = [
      makeScene({
        sceneId: "s1",
        status: "image_ready",
        imageUrl: "mock://imagen/s1.png",
        imageWidth: 1024,
        imageHeight: 1024,
      }),
    ];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('data-status="image_ready"');
    expect(html).toContain('role="img"');
    expect(html).toContain("scene-image-placeholder");
    expect(html).toContain("Image ready");
  });

  it("image_ready with https url: renders img element", () => {
    const scenes = [
      makeScene({
        sceneId: "s1",
        status: "image_ready",
        imageUrl: "https://cdn.example.com/scene-1.png",
        imageWidth: 1024,
        imageHeight: 768,
      }),
    ];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('data-status="image_ready"');
    expect(html).toContain("scene-image-asset");
    expect(html).toContain('src="https://cdn.example.com/scene-1.png"');
  });

  it("delayed with image: shows Ken Burns class", () => {
    const scenes = [
      makeScene({
        sceneId: "s1",
        status: "delayed",
        imageUrl: "mock://imagen/s1.png",
        imageWidth: 1024,
        imageHeight: 1024,
        fallbackActive: true,
      }),
    ];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('data-status="delayed"');
    expect(html).toContain("scene-ken-burns");
    expect(html).toContain("Creating something special...");
  });

  it("delayed with https image: renders img with Ken Burns class", () => {
    const scenes = [
      makeScene({
        sceneId: "s1",
        status: "delayed",
        imageUrl: "https://cdn.example.com/scene-1.png",
        imageWidth: 1024,
        imageHeight: 768,
        fallbackActive: true,
      }),
    ];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('data-status="delayed"');
    expect(html).toContain("scene-image-asset");
    expect(html).toContain("scene-ken-burns");
  });

  it("delayed without image: shows delayed placeholder (no Ken Burns)", () => {
    const scenes = [
      makeScene({
        sceneId: "s2",
        status: "delayed",
        fallbackActive: true,
      }),
    ];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('data-status="delayed"');
    expect(html).toContain("scene-delayed-placeholder");
    expect(html).not.toContain("scene-ken-burns");
  });

  it("video_ready: shows video placeholder with play icon", () => {
    const scenes = [
      makeScene({
        sceneId: "s2",
        status: "video_ready",
        videoUrl: "mock://veo/s2.mp4",
        videoDuration: 8,
      }),
    ];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('data-status="video_ready"');
    expect(html).toContain("▶");
    expect(html).toContain("Video ready!");
    expect(html).toContain("scene-video-duration");
    expect(html).toMatch(/8.*s/);
  });

  it("video_ready with https url: renders video element", () => {
    const scenes = [
      makeScene({
        sceneId: "s2",
        status: "video_ready",
        videoUrl: "https://cdn.example.com/scene-2.mp4",
        videoDuration: 8,
      }),
    ];
    const html = renderToString(<NarrativeTimeline scenes={scenes} />);
    expect(html).toContain('data-status="video_ready"');
    expect(html).toContain("scene-video-asset");
    expect(html).toContain('src="https://cdn.example.com/scene-2.mp4"');
  });
});
