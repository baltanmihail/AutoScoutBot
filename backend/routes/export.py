import io
import pandas as pd
from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models import Startup, StartupScore, StartupFinancial

router = APIRouter(prefix="/api/export", tags=["export"])

@router.get("/startup/{startup_id}")
async def export_startup_xlsx(startup_id: str, session: AsyncSession = Depends(get_session)):
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

    # Sheet 1: General Info
    general_data = {
        "Показатель": [
            "ID", "Название", "ИНН", "ОГРН", "Год основания", "Статус", "Кластер",
            "Отрасли", "Технологии", "Описание компании",
            "TRL", "IRL", "MRL", "CRL", "Патенты", "Сайт"
        ],
        "Значение": [
            startup.id, startup.name, startup.inn, startup.ogrn, startup.year_founded, startup.status, startup.cluster,
            startup.industries, startup.technologies, startup.company_description,
            startup.trl, startup.irl, startup.mrl, startup.crl, startup.patents, startup.website
        ]
    }
    df_general = pd.DataFrame(general_data)

    # Sheet 2: Financials
    fin_data = []
    for f in fin_rows:
        fin_data.append({"Год": f.year, "Выручка": f.revenue, "Прибыль": f.profit})
    df_fin = pd.DataFrame(fin_data)

    # Sheet 3: ML Scores
    score_data = {"Показатель": [], "Балл (1-10)": []}
    if sc:
        score_data["Показатель"] = [
            "Общий рейтинг (Proxy)", "Зрелость технологий", "Инновационность",
            "Потенциал рынка", "Готовность команды", "Финансовое здоровье",
            "ML Общий балл"
        ]
        score_data["Балл (1-10)"] = [
            sc.score_overall, sc.score_tech_maturity, sc.score_innovation,
            sc.score_market_potential, sc.score_team_readiness, sc.score_financial_health,
            sc.ml_score
        ]
    df_scores = pd.DataFrame(score_data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_general.to_excel(writer, sheet_name="Общая информация", index=False)
        df_fin.to_excel(writer, sheet_name="Финансы", index=False)
        df_scores.to_excel(writer, sheet_name="Рейтинг и оценки", index=False)

    output.seek(0)

    filename = f"report_{startup.id}.xlsx"
    from urllib.parse import quote
    filename_safe = quote(f"report_{startup.name}.xlsx".replace(" ", "_").replace('"', ''))
    
    headers = {
        'Content-Disposition': f"attachment; filename*=utf-8''{filename_safe}"
    }

    return StreamingResponse(
        output,
        headers=headers,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )