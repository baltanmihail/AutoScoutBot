"""Score endpoint -- get detailed scores + SHAP explanation for a startup."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models import Startup, StartupScore, StartupFinancial, ExternalData
from backend.schemas import (
    ScoreRequest, ScoreResponse, FullScoreResponse, FinancialRecord,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/score", tags=["score"])


def _startup_to_feature_row(startup: Startup, financials: list) -> dict:
    """Convert ORM Startup + financials into a flat dict for the predictor."""
    row = {
        "name": startup.name,
        "company_description": startup.company_description or "",
        "project_description": startup.project_description or "",
        "product_description": startup.product_description or "",
        "technologies": startup.technologies or "",
        "industries": startup.industries or "",
        "product_names": startup.product_names or "",
        "project_names": startup.project_names or "",
        "patents": startup.patents or "",
        "cluster": startup.cluster or "",
        "status": startup.status or "",
        "year_founded": startup.year_founded or "",
        "trl": startup.trl,
        "irl": startup.irl,
        "mrl": startup.mrl,
        "crl": startup.crl,
    }
    for fin in financials:
        row[f"revenue_{fin.year}"] = fin.revenue
        row[f"profit_{fin.year}"] = fin.profit
    return row


@router.post("/", response_model=ScoreResponse)
async def get_score(
    req: ScoreRequest,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Startup, StartupScore)
        .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
        .where(Startup.id == req.startup_id)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Startup not found")

    startup, sc = row

    # Load financials for ML prediction
    fin_rows = (
        await session.execute(
            select(StartupFinancial).where(StartupFinancial.startup_id == startup.id)
        )
    ).scalars().all()

    scores = {}
    explanation = None
    ml_score_val = sc.ml_score if sc else None

    if sc:
        scores = {
            "tech_maturity": sc.score_tech_maturity,
            "innovation": sc.score_innovation,
            "market_potential": sc.score_market_potential,
            "team_readiness": sc.score_team_readiness,
            "financial_health": sc.score_financial_health,
            "overall": sc.score_overall,
        }

    # Try ML prediction + SHAP explanation
    try:
        from scoring.predictor import get_predictor

        predictor = get_predictor()
        if predictor.is_ready:
            feature_row = _startup_to_feature_row(startup, fin_rows)
            ml_scores = predictor.predict(feature_row)
            ml_score_val = ml_scores.get("overall")

            # Merge ML scores into response (ML scores override proxy scores)
            scores.update({
                "ml_overall": ml_scores.get("overall", 0),
                "ml_tech_maturity": ml_scores.get("tech_maturity", 0),
                "ml_innovation": ml_scores.get("innovation", 0),
                "ml_market_potential": ml_scores.get("market_potential", 0),
                "ml_team_readiness": ml_scores.get("team_readiness", 0),
                "ml_financial_health": ml_scores.get("financial_health", 0),
            })

            # SHAP explanation for the overall score
            shap_exp = predictor.explain(feature_row, target="overall", top_n=8)
            if shap_exp:
                explanation = shap_exp

            # Update ML score in DB
            if sc and ml_score_val:
                sc.ml_score = ml_score_val
                sc.ml_model_version = predictor.version
                await session.commit()

    except Exception as e:
        logger.warning("ML prediction failed for %s: %s", req.startup_id, e)

    return ScoreResponse(
        startup_id=startup.id,
        name=startup.name,
        scores=scores,
        ml_score=ml_score_val,
        explanation=explanation,
    )


@router.get("/by-name/{name}")
async def score_by_name(
    name: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Score a startup by name (case-insensitive search).
    Returns ML scores + SHAP explanation without needing the startup ID.
    Great for quick lookups from the Telegram bot or external integrations.
    """
    stmt = select(Startup).where(Startup.name.ilike(f"%{name}%")).limit(5)
    results = (await session.execute(stmt)).scalars().all()

    if not results:
        raise HTTPException(status_code=404, detail=f"No startup matching '{name}'")

    scored = []
    for startup in results:
        fin_rows = (
            await session.execute(
                select(StartupFinancial).where(StartupFinancial.startup_id == startup.id)
            )
        ).scalars().all()

        feature_row = _startup_to_feature_row(startup, fin_rows)
        ml_scores = {}
        explanation = None

        try:
            from scoring.predictor import get_predictor
            predictor = get_predictor()
            if predictor.is_ready:
                ml_scores = predictor.predict(feature_row)
                explanation = predictor.explain(feature_row, target="overall", top_n=5)
        except Exception:
            pass

        scored.append({
            "id": startup.id,
            "name": startup.name,
            "cluster": startup.cluster,
            "status": startup.status,
            "ml_scores": ml_scores,
            "explanation": explanation,
        })

    return {"query": name, "results": scored}


@router.post("/full", response_model=FullScoreResponse)
async def get_full_score(
    req: ScoreRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    Phase 4: Full scoring pipeline with all dimensions, SHAP for each,
    financial history, and external data summary.
    """
    stmt = (
        select(Startup, StartupScore)
        .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
        .where(Startup.id == req.startup_id)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Startup not found")

    startup, sc = row

    # Load financials
    fin_rows = (
        await session.execute(
            select(StartupFinancial)
            .where(StartupFinancial.startup_id == startup.id)
            .order_by(StartupFinancial.year.desc())
        )
    ).scalars().all()

    financials = [
        FinancialRecord(year=f.year, revenue=f.revenue, profit=f.profit)
        for f in fin_rows
    ]

    # Proxy scores
    proxy_scores = {}
    if sc:
        proxy_scores = {
            "tech_maturity": sc.score_tech_maturity,
            "innovation": sc.score_innovation,
            "market_potential": sc.score_market_potential,
            "team_readiness": sc.score_team_readiness,
            "financial_health": sc.score_financial_health,
            "overall": sc.score_overall,
        }

    # ML scores + SHAP
    ml_scores = None
    ml_version = None
    explanation = None
    all_explanations = None

    try:
        from scoring.predictor import get_predictor

        predictor = get_predictor()
        if predictor.is_ready:
            feature_row = _startup_to_feature_row(startup, fin_rows)
            ml_scores = predictor.predict(feature_row)
            ml_version = predictor.version

            explanation = predictor.explain(feature_row, target="overall", top_n=8)
            all_explanations = predictor.explain_all(feature_row, top_n=5)

            # Update DB
            if sc:
                sc.ml_score = ml_scores.get("overall")
                sc.ml_model_version = ml_version
                await session.flush()

    except Exception as e:
        logger.warning("ML prediction failed for full score %s: %s", req.startup_id, e)

    # External data summary
    external_data = None
    try:
        ext_rows = (
            await session.execute(
                select(ExternalData)
                .where(ExternalData.startup_id == startup.id)
                .order_by(ExternalData.fetched_at.desc())
            )
        ).scalars().all()

        if ext_rows:
            external_data = {}
            for ext in ext_rows:
                try:
                    data = json.loads(ext.data_json)
                except (json.JSONDecodeError, TypeError):
                    data = {}
                external_data[ext.source] = {
                    "fetched_at": ext.fetched_at.isoformat() if ext.fetched_at else None,
                    "authority": ext.source_authority,
                    "data": data,
                }
    except Exception as e:
        logger.debug("Failed to load external data: %s", e)

    await session.commit()

    return FullScoreResponse(
        startup_id=startup.id,
        name=startup.name,
        proxy_scores=proxy_scores,
        ml_scores=ml_scores,
        ml_model_version=ml_version,
        explanation=explanation,
        all_explanations=all_explanations,
        financials=financials,
        external_data=external_data,
    )
