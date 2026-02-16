"""
Migration script: SkolkovoStartups.csv + labeled scores -> PostgreSQL.

Usage:
    python -m backend.migrate_csv                    # uses default paths
    python -m backend.migrate_csv --csv path.csv     # custom CSV
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoring.labeler import label_dataframe, _parse_money, _parse_level

from backend.database import engine, async_session, init_db, Base
from backend.models import Startup, StartupScore, StartupFinancial


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


async def migrate(csv_path: str):
    print("Initialising database schema ...")
    await init_db()

    # --- read raw CSV ---
    raw = pd.read_csv(csv_path, encoding="utf-8", dtype=str).fillna("")
    for ru, en in COLUMN_MAP.items():
        if ru in raw.columns:
            raw.rename(columns={ru: en}, inplace=True)

    # --- compute labels ---
    print("Computing proxy labels ...")
    labels = label_dataframe(csv_path)
    label_map = {row["id"]: row for _, row in labels.iterrows()}

    print(f"Migrating {len(raw)} startups ...")

    async with async_session() as session:
        for idx, row in raw.iterrows():
            import hashlib

            sid = hashlib.md5(str(row.get("name", "")).encode()).hexdigest()

            year_val = None
            y = str(row.get("year_founded", "")).strip()
            if y.isdigit() and 1900 <= int(y) <= 2030:
                year_val = int(y)

            startup = Startup(
                id=sid,
                name=str(row.get("name", "")),
                website=str(row.get("website", "")),
                company_description=str(row.get("company_description", "")),
                project_description=str(row.get("project_description", "")),
                product_description=str(row.get("product_description", "")),
                full_legal_name=str(row.get("full_legal_name", "")),
                inn=str(row.get("inn", "")),
                ogrn=str(row.get("ogrn", "")),
                year_founded=year_val,
                status=str(row.get("status", "")),
                cluster=str(row.get("cluster", "")),
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

    print("Migration complete.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(ROOT / "SkolkovoStartups.csv"))
    args = parser.parse_args()
    asyncio.run(migrate(args.csv))


if __name__ == "__main__":
    main()
