"""TDD-first tests for AssetStore.

AssetStore responsibilities:
- Sanitize scene_id filenames (no path traversal, safe chars only).
- Save image/video bytes to disk via asyncio.to_thread (non-blocking I/O).
- Return public HTTP URLs pointing to /assets/{filename}.
- Create assets directory if it does not exist.

All tests run without a real genai.Client.  File-system operations use
pytest tmp_path so nothing leaks to disk permanently.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.asset_store import AssetStore, _sanitize_scene_id


# ── Sanitization ──────────────────────────────────────────────────────────────


def test_sanitize_scene_id_strips_path_separators():
    """`../` and `/` are replaced — no directory traversal."""
    assert "/" not in _sanitize_scene_id("../../etc/passwd")
    assert ".." not in _sanitize_scene_id("../secret")


def test_sanitize_scene_id_keeps_alphanumeric_hyphen_underscore():
    assert _sanitize_scene_id("scene-1_abc") == "scene-1_abc"


def test_sanitize_scene_id_replaces_spaces_and_specials():
    result = _sanitize_scene_id("scene 1!@#$")
    assert " " not in result
    assert "!" not in result


def test_sanitize_scene_id_truncates_to_max_length():
    long_id = "a" * 200
    result = _sanitize_scene_id(long_id)
    assert len(result) <= 64


# ── AssetStore directory creation ────────────────────────────────────────────


def test_asset_store_creates_directory(tmp_path: Path):
    assets_dir = tmp_path / "subdir" / "assets"
    assert not assets_dir.exists()
    AssetStore(assets_dir=assets_dir, base_url="http://localhost:8000")
    assert assets_dir.is_dir()


# ── URL generation ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_image_returns_https_url(tmp_path: Path):
    """save_image must return a URL with /assets/ path and .png extension."""
    store = AssetStore(assets_dir=tmp_path, base_url="http://localhost:8000")

    saved_paths: list[str] = []

    def fake_save(path: str) -> None:
        saved_paths.append(path)
        Path(path).write_bytes(b"fake-png")

    url = await store.save_image("scene-1", fake_save)

    assert url.startswith("http://localhost:8000/assets/")
    assert url.endswith(".png")
    assert "scene_1" in url or "scene-1" in url


@pytest.mark.asyncio
async def test_save_video_returns_https_url(tmp_path: Path):
    """save_video must return a URL with /assets/ path and .mp4 extension."""
    store = AssetStore(assets_dir=tmp_path, base_url="http://localhost:8000")

    def fake_save(path: str) -> None:
        Path(path).write_bytes(b"fake-mp4")

    url = await store.save_video("scene-1", fake_save)

    assert url.startswith("http://localhost:8000/assets/")
    assert url.endswith(".mp4")


@pytest.mark.asyncio
async def test_save_image_actually_writes_file(tmp_path: Path):
    """save_image must persist bytes at the resolved path."""
    store = AssetStore(assets_dir=tmp_path, base_url="http://localhost:8000")
    CONTENT = b"\x89PNG\r\n\x1a\n"

    def fake_save(path: str) -> None:
        Path(path).write_bytes(CONTENT)

    await store.save_image("scene-42", fake_save)

    files = list(tmp_path.glob("*.png"))
    assert len(files) == 1
    assert files[0].read_bytes() == CONTENT


@pytest.mark.asyncio
async def test_save_video_actually_writes_file(tmp_path: Path):
    """save_video must persist bytes at the resolved path."""
    store = AssetStore(assets_dir=tmp_path, base_url="http://localhost:8000")
    CONTENT = b"fake-video-bytes"

    def fake_save(path: str) -> None:
        Path(path).write_bytes(CONTENT)

    await store.save_video("scene-99", fake_save)

    files = list(tmp_path.glob("*.mp4"))
    assert len(files) == 1
    assert files[0].read_bytes() == CONTENT


@pytest.mark.asyncio
async def test_save_is_non_blocking(tmp_path: Path):
    """save_image must use asyncio.to_thread so the event loop is not blocked."""
    store = AssetStore(assets_dir=tmp_path, base_url="http://localhost:8000")

    import threading

    thread_ids: list[int] = []

    def blocking_save(path: str) -> None:
        thread_ids.append(threading.get_ident())
        Path(path).write_bytes(b"x")

    main_thread_id = threading.get_ident()
    await store.save_image("scene-nonblocking", blocking_save)

    assert len(thread_ids) == 1
    # The save ran in a worker thread, NOT the main (event-loop) thread.
    assert thread_ids[0] != main_thread_id, (
        "save_image must delegate blocking I/O to asyncio.to_thread, not run on the event loop thread"
    )


# ── Traversal safety ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malicious_scene_id_cannot_escape_assets_dir(tmp_path: Path):
    """A path-traversal scene_id must NOT resolve outside assets_dir."""
    store = AssetStore(assets_dir=tmp_path, base_url="http://localhost:8000")

    def noop_save(path: str) -> None:
        pass

    url = await store.save_image("../../etc/passwd", noop_save)
    # URL must still point inside /assets/ and not contain traversal segments.
    assert "/assets/" in url
    assert ".." not in url
