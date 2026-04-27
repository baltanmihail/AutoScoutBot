import asyncio
import hashlib
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, select

from backend.database import async_session, init_db
from backend.models import Startup, StartupFinancial, StartupScore
from scoring.labeler import label_dataframe, _parse_money, _parse_level

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "db" / "SkolkovoStartups.csv"
LABELED_PATH = ROOT / "scoring" / "labeled_startups.csv"

COLUMN_MAP = {
    "Название компании": "name",
    "Сайт": "website",
    "Описание компании": "company_description",
    "Описание проектов": "project_description",
    "Описание продуктов": "product_description",
    "Полное юр. название": "full_legal_name",
    "ИНН": "inn",
    "ОГРН": "ogrn",
    "Год основания": "year_founded",
    "Статус организации": "status",
    "Кластер": "cluster",
    "Сферы деятельности": "category",
    "Регионы присутствия": "region",
    "Технологии проекта": "technologies",
    "Отрасли применения": "industries",
    "Названия продуктов": "product_names",
    "Названия проектов": "project_names",
    "Патенты": "patents",
    "TRL (по продуктам)": "trl_raw",
    "IRL - Уровень": "irl_raw",
    "MRL (по продуктам)": "mrl_raw",
    "CRL - Уровень": "crl_raw",
}

YEARS = [2025, 2024, 2023, 2022, 2021, 2020]

def _cut(value, max_len: int):
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[:max_len]
    return text

async def main():
    await init_db()

    print("Reading data...")
    raw = pd.read_csv(CSV_PATH, encoding="utf-8", dtype=str).fillna("")
    for ru, en in COLUMN_MAP.items():
        if ru in raw.columns:
            raw.rename(columns={ru: en}, inplace=True)

    print("Computing/reading proxy labels ...")
    labels = label_dataframe(str(CSV_PATH))
    label_map = {row["id"]: row for _, row in labels.iterrows()}

    async with async_session() as session:
        existing_count = (await session.execute(select(Startup.id))).scalars().first()
        if existing_count:
            print("Clearing old data...")
            await session.execute(delete(StartupFinancial))
            await session.execute(delete(StartupScore))
            await session.execute(delete(Startup))
            await session.commit()
            
        print(f"Migrating {len(raw)} startups...")

        seen_ids = set()

        for idx, row in raw.iterrows():
            name_val = str(row.get("name", "")).strip()
            sid = hashlib.md5(name_val.encode()).hexdigest()

            if sid in seen_ids:
                continue
            seen_ids.add(sid)

            year_val = None
            y = str(row.get("year_founded", "")).strip()
            if y.isdigit() and 1900 <= int(y) <= 2030:
                year_val = int(y)

            startup = Startup(
                id=sid,
                name=_cut(row.get("name", ""), 512),
                website=_cut(row.get("website", ""), 512),
                company_description=str(row.get("company_description", "")),
                project_description=str(row.get("project_description", "")),
                product_description=str(row.get("product_description", "")),
                full_legal_name=_cut(row.get("full_legal_name", ""), 1024),
                inn=_cut(row.get("inn", ""), 20),
                ogrn=_cut(row.get("ogrn", ""), 20),
                year_founded=year_val,
                status=_cut(row.get("status", ""), 50),
                cluster=_cut(row.get("cluster", ""), 50),
                category=str(row.get("category", "")),
                region=str(row.get("region", "")),
                technologies=str(row.get("technologies", "")),
                industries=str(row.get("industries", "")),
                product_names=str(row.get("product_names", "")),
                project_names=str(row.get("project_names", "")),
                patents=str(row.get("patents", "")),
                trl=_parse_level(row.get("trl_raw")),
                irl=_parse_level(row.get("irl_raw")),
                mrl=_parse_level(row.get("mrl_raw")),
                crl=_parse_level(row.get("crl_raw")),
            )
            session.add(startup)

            # Scores
            lbl = label_map.get(sid, {})
            if lbl is not None and len(lbl) > 0:
                score = StartupScore(
                    startup_id=sid,
                    score_tech_maturity=float(lbl.get("score_tech_maturity", 0)),
                    score_innovation=float(lbl.get("score_innovation", 0)),
                    score_market_potential=float(lbl.get("score_market_potential", 0)),
                    score_team_readiness=float(lbl.get("score_team_readiness", 0)),
                    score_financial_health=float(lbl.get("score_financial_health", 0)),
                    score_overall=float(lbl.get("score_overall", 0)),
                )
                session.add(score)

            # Financials
            for y in YEARS:
                rev = _parse_money(row.get(f"Выручка {y}", row.get(f"revenue_{y}", "")))
                prof = _parse_money(row.get(f"Прибыль {y}", row.get(f"profit_{y}", "")))
                if rev > 0 or prof > 0:
                    fin = StartupFinancial(
                        startup_id=sid,
                        year=y,
                        revenue=rev,
                        profit=prof,
                    )
                    session.add(fin)

            if (idx + 1) % 500 == 0:
                await session.flush()
                print(f"  ... {idx + 1} / {len(raw)}")

        await session.commit()
    print("Full DB Migration complete.")

if __name__ == "__main__":
    asyncio.run(main())