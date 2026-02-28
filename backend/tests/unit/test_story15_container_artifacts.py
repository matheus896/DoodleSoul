from __future__ import annotations

from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_backend_dockerfile_exists_and_exposes_port_8000() -> None:
    dockerfile = _backend_root() / "Dockerfile"
    assert dockerfile.exists(), "backend/Dockerfile must exist for Story 1.5"

    content = dockerfile.read_text(encoding="utf-8")
    assert "FROM python:3.11" in content
    assert "uvicorn" in content
    assert "app.main:app" in content
    assert "EXPOSE 8000" in content


def test_backend_dockerignore_exists_with_expected_entries() -> None:
    dockerignore = _backend_root() / ".dockerignore"
    assert dockerignore.exists(), "backend/.dockerignore must exist for Story 1.5"

    lines = {
        line.strip()
        for line in dockerignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert ".venv" in lines
    assert "__pycache__" in lines
    assert ".pytest_cache" in lines
