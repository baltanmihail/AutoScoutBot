"""Admin endpoint -- system statistics, enrichment, model management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models import Startup, StartupScore, ExternalData, User, Query
from backend.schemas import SystemStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=SystemStats)
async def system_stats(session: AsyncSession = Depends(get_session)):
    total_startups = (await session.execute(select(func.count(Startup.id)))).scalar() or 0
    total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
    total_queries = (await session.execute(select(func.count(Query.id)))).scalar() or 0
    avg_score = (
        await session.execute(select(func.avg(StartupScore.score_overall)))
    ).scalar() or 0

    # Find latest ML model version
    ml_ver = (
        await session.execute(
            select(StartupScore.ml_model_version)
            .where(StartupScore.ml_model_version.isnot(None))
            .order_by(StartupScore.updated_at.desc())
            .limit(1)
        )
    ).scalar()

    return SystemStats(
        total_startups=total_startups,
        total_users=total_users,
        total_queries=total_queries,
        avg_overall_score=round(float(avg_score), 2),
        ml_model_version=ml_ver,
    )


@router.get("/enrichment/status")
async def enrichment_status(session: AsyncSession = Depends(get_session)):
    """Get status of data enrichment (external data coverage)."""
    total = (await session.execute(select(func.count(Startup.id)))).scalar() or 0

    # Count startups with data from each source
    source_counts = {}
    for source in ["egrul", "checko", "bfo", "moex", "news_rbc", "news_interfax", "news_tass"]:
        cnt = (
            await session.execute(
                select(func.count(func.distinct(ExternalData.startup_id)))
                .where(ExternalData.source == source)
            )
        ).scalar() or 0
        source_counts[source] = cnt

    # Scheduler status
    scheduler_running = False
    try:
        from backend.parsers.scheduler import get_enrichment_scheduler
        scheduler_running = get_enrichment_scheduler().is_running
    except Exception:
        pass

    return {
        "total_startups": total,
        "enrichment_coverage": source_counts,
        "scheduler_running": scheduler_running,
    }


@router.post("/enrich/{startup_id}")
async def enrich_startup(startup_id: str):
    """Trigger on-demand enrichment for a single startup."""
    try:
        from backend.parsers.scheduler import enrich_single_startup
        results = await enrich_single_startup(startup_id)
        return {"startup_id": startup_id, "results": results}
    except Exception as e:
        logger.error("On-demand enrichment failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ml/status")
async def ml_model_status():
    """Get ML model status and metrics."""
    try:
        from scoring.predictor import get_predictor

        predictor = get_predictor()
        if not predictor.is_ready:
            return {"ready": False, "message": "No trained models found"}

        return {
            "ready": True,
            "version": predictor.version,
            "targets": list(predictor._models.keys()),
            "meta": {
                k: {
                    "version": v.get("version"),
                    "cv_metrics": v.get("cv_metrics"),
                }
                for k, v in predictor._meta.items()
            },
        }
    except Exception as e:
        return {"ready": False, "error": str(e)}
