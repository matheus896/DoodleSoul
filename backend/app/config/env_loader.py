from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def _iter_env_files() -> list[Path]:
    backend_root = Path(__file__).resolve().parents[2]
    project_root = backend_root.parent
    return [project_root / ".env", backend_root / ".env"]


def load_env_once() -> None:
    global _LOADED
    if _LOADED:
        return

    for env_file in _iter_env_files():
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    _LOADED = True
