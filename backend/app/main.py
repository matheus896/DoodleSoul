from fastapi import FastAPI

from app.api.session import router as session_router
from app.api.websockets import router as ws_router


app = FastAPI(title="A(I)nimism Studio Backend")
app.include_router(session_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
