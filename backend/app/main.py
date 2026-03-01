from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.session import init_vision_deriver
from app.api.session import router as session_router
from app.api.websockets import router as ws_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Application lifespan: initialize services at startup."""
    init_vision_deriver()
    yield


app = FastAPI(title="A(I)nimism Studio Backend", lifespan=lifespan)
app.include_router(session_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
