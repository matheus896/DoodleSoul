"""AssetStore — Secure local static asset storage with URL resolution.

Responsibilities:
    - Sanitize ``scene_id`` values to safe filenames (no path traversal).
    - Save image/video artifacts via asyncio.to_thread (non-blocking I/O).
    - Return public HTTP URLs aligned with the FastAPI /assets StaticFiles mount.
    - Create the assets directory on first use.

Design invariants:
    - Self-contained: no dependency on bridge, audio, or WebSocket code.
    - Stateless URL factory: URL is always derivable from scene_id alone.
    - Thread-safe writes: each save goes through asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_NAME_LEN = 64


def _sanitize_scene_id(scene_id: str) -> str:
    """Replace any non-safe character with ``_``, truncate to _MAX_NAME_LEN.

    Guarantees no path-traversal sequences (``..``, ``/``, etc.) survive.
    """
    safe = _SAFE_NAME_RE.sub("_", scene_id)
    return safe[:_MAX_NAME_LEN]


# ---------------------------------------------------------------------------
# AssetStore
# ---------------------------------------------------------------------------


class AssetStore:
    """Manages local static asset storage and HTTP URL generation.

    Parameters
    ----------
    assets_dir:
        Absolute directory where artifacts are persisted.  Created on
        instantiation if it does not exist.
    base_url:
        Public base URL of the backend (e.g. ``http://localhost:8000``).
        Must match the host that serves the ``/assets`` StaticFiles mount.
    """

    def __init__(self, *, assets_dir: Path, base_url: str) -> None:
        self._assets_dir = assets_dir
        self._base_url = base_url.rstrip("/")
        assets_dir.mkdir(parents=True, exist_ok=True)

    # ── Public properties ────────────────────────────────────────────────

    @property
    def assets_dir(self) -> Path:
        """Resolved directory where assets are stored."""
        return self._assets_dir

    # ── Async save helpers ───────────────────────────────────────────────

    async def save_image(self, scene_id: str, save_fn: Callable[[str], None]) -> str:
        """Save image artifact and return its public URL.

        Parameters
        ----------
        scene_id:
            Logical scene identifier.  Sanitized before use.
        save_fn:
            Callable that accepts an absolute path string and writes the
            image bytes there (e.g. ``genai_image.save``).  Called inside
            ``asyncio.to_thread`` so heavy I/O never blocks the event loop.

        Returns
        -------
        str
            Public URL: ``{base_url}/assets/{safe_scene_id}_imagen_still.png``
        """
        path = self._image_path(scene_id)
        await asyncio.to_thread(save_fn, str(path))
        return self._url(path)

    async def save_video(self, scene_id: str, save_fn: Callable[[str], None]) -> str:
        """Save video artifact and return its public URL.

        Parameters
        ----------
        scene_id:
            Logical scene identifier.  Sanitized before use.
        save_fn:
            Callable that accepts an absolute path string and writes the
            video bytes there (e.g. ``genai_video.save``).  Called inside
            ``asyncio.to_thread``.

        Returns
        -------
        str
            Public URL: ``{base_url}/assets/{safe_scene_id}_social_story.mp4``
        """
        path = self._video_path(scene_id)
        await asyncio.to_thread(save_fn, str(path))
        return self._url(path)

    # ── Private helpers ──────────────────────────────────────────────────

    def _image_path(self, scene_id: str) -> Path:
        safe = _sanitize_scene_id(scene_id)
        return self._assets_dir / f"{safe}_imagen_still.png"

    def _video_path(self, scene_id: str) -> Path:
        safe = _sanitize_scene_id(scene_id)
        return self._assets_dir / f"{safe}_social_story.mp4"

    def _url(self, path: Path) -> str:
        """Build a public URL from a resolved artifact path."""
        return f"{self._base_url}/assets/{path.name}"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_asset_store() -> AssetStore:
    """Build an ``AssetStore`` from environment configuration.

    Environment variables:
        ANIMISM_ASSETS_DIR      — Absolute or relative path for asset storage.
                                  Relative paths are resolved from the backend
                                  package root.  Defaults to ``assets/``.
        ANIMISM_ASSET_BASE_URL  — Public base URL of the backend.
                                  Defaults to ``http://localhost:8000``.
    """
    from app.config.env_loader import load_env_once  # noqa: PLC0415

    load_env_once()

    raw_dir = os.getenv("ANIMISM_ASSETS_DIR", "assets")
    assets_dir = Path(raw_dir)
    if not assets_dir.is_absolute():
        # Resolve relative to backend package root (one level above app/)
        backend_root = Path(__file__).resolve().parents[2]
        assets_dir = backend_root / raw_dir

    base_url = os.getenv("ANIMISM_ASSET_BASE_URL", "http://localhost:8000")
    return AssetStore(assets_dir=assets_dir, base_url=base_url)
