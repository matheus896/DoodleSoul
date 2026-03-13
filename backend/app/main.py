import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.session import init_vision_deriver
from app.api.session import router as session_router
from app.api.websockets import router as ws_router
from app.config.env_loader import load_env_once
from app.services.asset_store import build_asset_store


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Application lifespan: initialize services at startup."""
    load_env_once()

    # WS6 — modular log level: INFO (dev default), WARNING (prod)
    # Python's logging requires an explicit handler; without one, INFO logs
    # are silently discarded (lastResort only handles WARNING+).
    log_level = os.getenv("ANIMISM_LOG_LEVEL", "INFO").upper()
    app_logger = logging.getLogger("app")
    app_logger.setLevel(getattr(logging, log_level, logging.INFO))
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)-8s %(name)s: %(message)s")
        )
        app_logger.addHandler(handler)

    init_vision_deriver()

    # Mount the local static assets directory so generated media is publicly
    # reachable at GET /assets/{filename}.  The directory is created by
    # AssetStore if it does not yet exist.  Configuration via env vars:
    #   ANIMISM_ASSETS_DIR      — local path (default: <backend>/assets/)
    #   ANIMISM_ASSET_BASE_URL  — public base URL (default: http://localhost:8000)
    asset_store = build_asset_store()
    application.mount(
        "/assets",
        StaticFiles(directory=str(asset_store.assets_dir)),
        name="assets",
    )
    application.state.asset_store = asset_store

    yield


app = FastAPI(title="A(I)nimism Studio Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon demo — restrict in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(session_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
