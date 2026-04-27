from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, select

from backend.database import async_session, init_db
from backend.models import Startup, StartupFinancial, StartupScore


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_CSV = ROOT / "external_startups.csv"
LABELED_CSV = ROOT / "scoring" / "labeled_startups.csv"


def _to_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def _to_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _cut(value, max_len: int):
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


async def main():
    await init_db()

    if not EXTERNAL_CSV.exists():
        raise FileNotFoundError(f"Missing file: {EXTERNAL_CSV}")
    if not LABELED_CSV.exists():
        raise FileNotFoundError(f"Missing file: {LABELED_CSV}")

    external_df = pd.read_csv(EXTERNAL_CSV).fillna("")
    labeled_df = pd.read_csv(LABELED_CSV).fillna("")

    score_by_id = {str(r["id"]): r for _, r in labeled_df.iterrows()}

    async with async_session() as session:
        existing_count = (await session.execute(select(Startup.id))).scalars().first()
        if existing_count:
            await session.execute(delete(StartupFinancial))
            await session.execute(delete(StartupScore))
            await session.execute(delete(Startup))
            await session.flush()

        rows_added = 0
        for _, row in external_df.iterrows():
            startup_id = str(row.get("skolkovo_id", "")).strip()
            if not startup_id:
                continue

            name = str(row.get("name", "")).strip()
            if not name:
                continue

            status = "active" if str(row.get("is_active", "")).lower() == "true" else str(row.get("status", "")).strip()
            okved = str(row.get("okved", "")).strip()
            fin_years = str(row.get("fin_years", "")).strip()
            latest_year = None
            if fin_years:
                try:
                    latest_year = int(fin_years.split("-")[-1])
                except Exception:
                    latest_year = None

            startup = Startup(
                id=startup_id,
                name=_cut(name, 512),
                inn=_cut(row.get("inn", ""), 20),
                full_legal_name=_cut(str(row.get("egrul_name", "")).strip() or name, 1024),
                status=_cut(status or "active", 50),
                cluster="",
                company_description=_cut(okved, 20000),
                technologies=_cut(okved, 20000),
                industries=_cut(okved, 20000),
                year_founded=_to_int(row.get("year_founded", 0), 0) or None,
                trl=0,
                irl=0,
                mrl=0,
                crl=0,
            )
            session.add(startup)

            score_row = score_by_id.get(startup_id)
            if score_row is not None:
                score = StartupScore(
                    startup_id=startup_id,
                    score_tech_maturity=_to_float(score_row.get("score_tech_maturity", 0)),
                    score_innovation=_to_float(score_row.get("score_innovation", 0)),
                    score_market_potential=_to_float(score_row.get("score_market_potential", 0)),
                    score_team_readiness=_to_float(score_row.get("score_team_readiness", 0)),
                    score_financial_health=_to_float(score_row.get("score_financial_health", 0)),
                    score_overall=_to_float(score_row.get("score_overall", 0)),
                    ml_score=_to_float(score_row.get("score_overall", 0)),
                )
                session.add(score)

                startup.trl = _to_int(score_row.get("trl", 0), 0)
                startup.irl = _to_int(score_row.get("irl", 0), 0)
                startup.mrl = _to_int(score_row.get("mrl", 0), 0)
                startup.crl = _to_int(score_row.get("crl", 0), 0)
                startup.cluster = _cut(score_row.get("cluster", ""), 50)

            revenue_latest = _to_float(row.get("revenue_latest", 0))
            profit_latest = _to_float(row.get("profit_latest", 0))
            if latest_year and (revenue_latest or profit_latest):
                session.add(
                    StartupFinancial(
                        startup_id=startup_id,
                        year=latest_year,
                        revenue=revenue_latest,
                        profit=profit_latest,
                    )
                )

            rows_added += 1
            if rows_added % 1000 == 0:
                await session.flush()
                print(f"Loaded {rows_added} startups...")

        await session.commit()
        print(f"Done. Loaded startups: {rows_added}")


if __name__ == "__main__":
    asyncio.run(main())
