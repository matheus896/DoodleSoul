from __future__ import annotations

import os

from app.config import env_loader


def test_load_env_once_sets_missing_values(monkeypatch, tmp_path) -> None:
    project_root = tmp_path / "repo"
    backend_root = project_root / "backend"
    target = backend_root / "app" / "config"
    target.mkdir(parents=True)

    (project_root / ".env").write_text("GOOGLE_API_KEY=test_key\n", encoding="utf-8")
    (backend_root / ".env").write_text("ANIMISM_LIVE_MODE=adk\n", encoding="utf-8")

    fake_file = target / "env_loader.py"
    fake_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(env_loader, "_LOADED", False)
    monkeypatch.setattr(env_loader, "__file__", str(fake_file))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANIMISM_LIVE_MODE", raising=False)

    env_loader.load_env_once()

    assert os.getenv("GOOGLE_API_KEY") == "test_key"
    assert os.getenv("ANIMISM_LIVE_MODE") == "adk"
