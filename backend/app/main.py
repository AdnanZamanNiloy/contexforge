"""
main.py — FastAPI application entry point for ContextForge.

Startup and shutdown are managed by a lifespan context manager (the
modern FastAPI pattern that replaces the deprecated @app.on_event hooks).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import Settings
from app.dependencies import close_all
from app.routes.github import router as github_router
from app.routes.ingest import router as ingest_router
from app.routes.query import router as query_router
from observability.tracer import configure_logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FIX #7/#8 — lifespan replaces deprecated @app.on_event("startup/shutdown")
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging on startup; release resources on shutdown."""
    # Startup
    configure_logging()
    logger.info("ContextForge starting up.")
    yield
    # Shutdown — FIX #4/#8
    await close_all()
    logger.info("ContextForge shut down cleanly.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def _get_allowed_origins() -> list[str]:
    """Return CORS allowed origins from settings.

    FIX #6 — wildcard origin with credentials is rejected by all browsers.
    ALLOWED_ORIGINS in .env should list explicit frontend origins in
    production (e.g. 'https://contextforge.example.com').
    Falls back to localhost only when not configured.
    """
    try:
        settings = Settings()
        origins = getattr(settings, "ALLOWED_ORIGINS", None)
        if origins:
            return origins if isinstance(origins, list) else [origins]
    except Exception:
        pass
    return ["http://localhost:5173", "http://localhost:3000"]


app = FastAPI(
    title="ContextForge",
    description=(
        "Production-grade RAG system with hybrid BM25 + dense retrieval, "
        "cross-encoder reranking, HyDE query expansion, and SSE streaming."
    ),
    version="1.0.0",
    lifespan=lifespan,  # FIX #7 — replaces @app.on_event
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

# FIX #6 — explicit origins; credentials=True only makes sense with non-wildcard
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],   # only what the API actually uses
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(ingest_router)
app.include_router(github_router)
app.include_router(query_router)


# ---------------------------------------------------------------------------
# FIX #9 — health check for Docker / k8s liveness probes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"], summary="Liveness check")
async def health() -> JSONResponse:
    """Return 200 OK when the application is running.

    Used by Docker healthcheck, k8s liveness probe, and load balancers.
    Does not verify storage or API connectivity — use /ready for that.
    """
    return JSONResponse({"status": "ok", "service": "contextforge"})