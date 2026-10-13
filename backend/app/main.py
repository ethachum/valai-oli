"""
Valaioli — FastAPI backend entry point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, jobs, metadata, playlist, tools, updater
from app.jobs import JobService
from app.services.manifest import ManifestService

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Application lifespan — create/shutdown singletons
# ──────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Valaioli backend starting up.")

    # Shared singletons stored on app.state
    manifest = ManifestService()
    app.state.manifest_service = manifest

    job_service = JobService(manifest)
    app.state.job_service = job_service

    logger.info("JobService ready.")
    yield

    logger.info("Valaioli backend shutting down.")
    await job_service.shutdown()


# ──────────────────────────────────────────────────────────────────────────────
# Application factory
# ──────────────────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Valaioli",
        description="Media download service API",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    # Tighten in production. During development allow Vite dev server variants.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    # ── Routers ────────────────────────────────────────────────────────────────
    app.include_router(health.router, prefix="/api")
    app.include_router(tools.router, prefix="/api")
    app.include_router(metadata.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(updater.router, prefix="/api")
    app.include_router(playlist.router, prefix="/api")

    return app


app = create_app()
