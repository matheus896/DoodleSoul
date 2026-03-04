from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.session import init_vision_deriver
from app.api.session import router as session_router
from app.api.websockets import router as ws_router
from app.services.asset_store import build_asset_store


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Application lifespan: initialize services at startup."""
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
app.include_router(session_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
