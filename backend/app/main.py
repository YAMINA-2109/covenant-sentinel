from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings

app = FastAPI(title="CovenantSentinel", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": True,
        "chat_model": settings.vultr_chat_model,
        "vultr_key_configured": bool(settings.vultr_api_key),
    }


# Single-process deployment: when the frontend has been built, serve it from
# here too (API routes above take precedence over the mount).
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="ui")
