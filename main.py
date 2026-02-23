# main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.setting import get_settings
from backend.core.logger import get_logger
from backend.api.routes import router
from backend.api.websocket import ws_router

settings = get_settings()
logger   = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events.
    Replaces deprecated @app.on_event("startup").
    """
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Starting codegen-poc")
    logger.info("Log level    : %s", settings.log_level)
    logger.info("Free chat threshold : %d turns", settings.free_chat_turn_threshold)
    logger.info("")
    logger.info("Agent model assignments:")
    logger.info("  %-20s → %s", "Conversationalist", settings.conversationalist_model)
    logger.info("  %-20s → %s", "Extractor",         settings.extractor_model)
    logger.info("  %-20s → %s", "Interviewer",        settings.interviewer_model)
    logger.info("  %-20s → %s", "Summariser",         settings.summariser_model)
    logger.info("  %-20s → %s (no LLM)", "Gap Finder", "—")
    logger.info("  %-20s → %s (no LLM)", "Dispatcher", "—")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down codegen-poc")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "codegen-poc",
    description = "Schema-Aware Conversational UI Code Generation — POC",
    version     = "0.1.0",
    lifespan    = lifespan,
)


# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:5173"],  # Vite dev server
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(router,    prefix="/api")
app.include_router(ws_router)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "0.1.0"}
