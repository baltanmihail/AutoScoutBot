from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import get_session
from backend.models import Startup, StartupScore, StartupFinancial, ExternalData
from backend.schemas import FullScoreResponse, StartupDetail, FinancialRecord
import json
import logging
from backend.routes.score import _startup_to_feature_row

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/startup", tags=["startup"])

@router.get("/{startup_id}", response_model=FullScoreResponse)
async def get_startup_details(startup_id: str, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Startup, StartupScore)
        .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
        .where(Startup.id == startup_id)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Startup not found")

    startup, sc = row

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
            
            if sc:
                sc.ml_score = ml_scores.get("overall")
                sc.ml_model_version = ml_version
                await session.commit()
    except Exception as e:
        logger.warning(f"ML prediction failed for full score {startup_id}: {e}")

    external_data = None
    z_score = None
    revenue_cagr = None
    team_size = None
    liquidity_ratio = None

    # Calculate CAGR
    if fin_rows:
        fins_sorted = sorted(fin_rows, key=lambda x: x.year)
        start_fin = next((f for f in fins_sorted if f.revenue and f.revenue > 0), None)
        end_fin = next((f for f in reversed(fins_sorted) if f.revenue and f.revenue > 0), None)
        if start_fin and end_fin and start_fin.year < end_fin.year:
            years = end_fin.year - start_fin.year
            if years > 0:
                revenue_cagr = (end_fin.revenue / start_fin.revenue) ** (1 / years) - 1

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
                    "authority": ext.source_authority,
                    "fetched_at": ext.fetched_at.isoformat() if ext.fetched_at else None,
                    "data": data,
                }
                
                # Parse specific metrics
                if ext.source == "checko":
                    if "data" in data and "sved_rab" in data["data"]:
                        team_size = data["data"]["sved_rab"].get("kol_rab")
                elif ext.source == "bfo" and data:
                    # Get latest year for financial ratios
                    latest_year = max(data.keys(), key=int)
                    bfo_fin = data[latest_year]
                    
                    ta = bfo_fin.get("total_assets", 0)
                    tl = bfo_fin.get("total_liabilities", 0)
                    ca = bfo_fin.get("current_assets", 0)
                    cl = bfo_fin.get("current_liabilities", 0)
                    re = bfo_fin.get("retained_earnings", 0)
                    ebit = bfo_fin.get("operating_profit", 0)
                    eq = bfo_fin.get("equity", 0)

                    # Z-Score (Altman for private non-manufacturing: 6.56T1 + 3.26T2 + 6.72T3 + 1.05T4)
                    if ta > 0:
                        t1 = (ca - cl) / ta
                        t2 = re / ta
                        t3 = ebit / ta
                        t4 = eq / tl if tl > 0 else 0
                        z_score = 6.56 * t1 + 3.26 * t2 + 6.72 * t3 + 1.05 * t4
                    
                    # Liquidity Ratio (Current Ratio)
                    if cl > 0:
                        liquidity_ratio = ca / cl

    except Exception as e:
        logger.warning(f"Failed to load external data for {startup_id}: {e}")

    return FullScoreResponse(
        startup_id=startup.id,
        startup=StartupDetail(
            id=startup.id,
            name=startup.name,
            cluster=startup.cluster,
            status=startup.status,
            year_founded=startup.year_founded,
            score_overall=sc.score_overall if sc else 0,
            ml_score=ml_scores.get("overall") if ml_scores else None,
            website=startup.website or "",
            company_description=startup.company_description or "",
            technologies=startup.technologies or "",
            industries=startup.industries or "",
            inn=startup.inn or "",
            ogrn=startup.ogrn or "",
            trl=startup.trl or 0,
            irl=startup.irl or 0,
            mrl=startup.mrl or 0,
            crl=startup.crl or 0,
            patent_count=len(startup.patents.split(",")) if startup.patents else 0,
        ),
        proxy_scores=proxy_scores,
        ml_scores=ml_scores,
        ml_model_version=ml_version,
        explanation=explanation,
        all_explanations=all_explanations,
        financials=financials,
        external_data=external_data,
        z_score=z_score,
        revenue_cagr=revenue_cagr,
        team_size=team_size,
        liquidity_ratio=liquidity_ratio
    )