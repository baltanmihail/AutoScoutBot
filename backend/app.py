"""
FastAPI application -- AutoScoutBot API server.

Run locally:
    uvicorn backend.app:app --reload --port 8000

On Railway the Procfile handles this (see docs/DEPLOY_RAILWAY.md).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.database import init_db
from backend.routes import search, score, admin

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise database schema
    await init_db()

    # Start background data enrichment scheduler (Phase 3)
    scheduler = None
    if os.environ.get("ENABLE_ENRICHMENT", "true").lower() in ("1", "true", "yes"):
        try:
            from backend.parsers.scheduler import get_enrichment_scheduler

            scheduler = get_enrichment_scheduler()
            interval = int(os.environ.get("ENRICHMENT_INTERVAL_HOURS", "6"))
            scheduler.start(interval_hours=interval)
            logger.info("Data enrichment scheduler started")
        except Exception as e:
            logger.warning("Failed to start enrichment scheduler: %s", e)

    # Pre-load ML predictor (Phase 2)
    try:
        from scoring.predictor import get_predictor

        predictor = get_predictor()
        if predictor.is_ready:
            logger.info("ML predictor loaded (version=%s)", predictor.version)
        else:
            logger.info("ML predictor not ready (no trained models found)")
    except Exception as e:
        logger.debug("ML predictor not available: %s", e)

    yield

    # Shutdown
    if scheduler and scheduler.is_running:
        scheduler.stop()


app = FastAPI(
    title="AutoScoutBot API",
    version="2.0.0",
    description="AI-powered startup scouting platform -- Skolkovo startup scoring & search",
    lifespan=lifespan,
)

app.include_router(search.router)
app.include_router(score.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    ml_ready = False
    try:
        from scoring.predictor import get_predictor
        ml_ready = get_predictor().is_ready
    except Exception:
        pass

    return {
        "status": "ok",
        "ml_model_ready": ml_ready,
    }
