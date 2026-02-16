"""
Phase 0 -- Proxy Labeling.

Generates ground-truth scores (1-10) for every startup in SkolkovoStartups.csv
using only the fields already present in the dataset.

Scores produced:
    tech_maturity   -- derived from TRL, IRL, MRL, CRL
    innovation      -- patents, AI-related tech, unique technologies
    market_potential -- IRL, industry breadth, product count
    team_readiness  -- CRL
    financial_health-- revenue / profit trends over 2020-2025
    overall         -- weighted combination of the above

Usage:
    python -m scoring.labeler          # writes scoring/labeled_startups.csv
    python -m scoring.labeler --json   # also writes .json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_level(raw) -> int:
    """Extract max numeric level (0-9) from strings like '8: Описание; 6: ...'."""
    if pd.isna(raw) or str(raw).strip() in ("", "0"):
        return 0
    s = str(raw).strip()
    if s.isdigit():
        return min(int(s), 9)
    nums = re.findall(r"(?:^|;\s*)(\d)\s*:", s)
    if nums:
        return max(int(n) for n in nums if 0 <= int(n) <= 9)
    m = re.search(r"[0-9]", s)
    return int(m.group()) if m else 0


def _parse_money(raw) -> float:
    """Parse profit/revenue string -> float (rubles)."""
    if pd.isna(raw):
        return 0.0
    s = str(raw).replace(" ", "").replace(",", ".").strip()
    if s in ("", "-", "0", "н/д", "н/а"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _clamp(val: float, lo: float = 1.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, val))


def _count_patents(raw) -> int:
    if pd.isna(raw) or not str(raw).strip():
        return 0
    return len([p for p in str(raw).split(";") if p.strip()])


def _count_items(raw) -> int:
    if pd.isna(raw) or not str(raw).strip():
        return 0
    return len([x for x in str(raw).split(";") if x.strip()])


AI_KEYWORDS = {
    "искусственный интеллект", "нейросеть", "машинное обучение",
    "deep learning", "нейронная сеть", "ai", "ml",
    "natural language processing", "computer vision", "nlp",
    "генеративный", "llm", "gpt", "neural network",
    "трансформер", "transformer",
}


def _has_ai(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in AI_KEYWORDS)


# ---------------------------------------------------------------------------
# scoring functions  (each returns 1-10)
# ---------------------------------------------------------------------------

def score_tech_maturity(trl: int, irl: int, mrl: int, crl: int) -> float:
    """Weighted average of readiness levels, scaled 1-10."""
    vals = [(trl, 0.35), (irl, 0.25), (mrl, 0.25), (crl, 0.15)]
    nonzero = [(v, w) for v, w in vals if v > 0]
    if not nonzero:
        return 1.0
    total_w = sum(w for _, w in nonzero)
    avg = sum(v * w for v, w in nonzero) / total_w  # 0-9 range
    return _clamp(avg * 10 / 9)  # -> 1-10


def score_innovation(
    trl: int,
    patent_count: int,
    has_ai_flag: bool,
    tech_count: int,
) -> float:
    """Higher for: high TRL + patents + AI + diverse technologies."""
    base = 1.0
    # TRL contribution (max +3)
    base += min(trl / 3, 3.0)
    # patents (max +2.5)
    if patent_count >= 10:
        base += 2.5
    elif patent_count >= 5:
        base += 2.0
    elif patent_count >= 1:
        base += 1.0
    # AI flag (+1.5)
    if has_ai_flag:
        base += 1.5
    # technology diversity (max +2)
    base += min(tech_count * 0.4, 2.0)
    return _clamp(base)


def score_market_potential(
    irl: int,
    industry_count: int,
    product_count: int,
    has_revenue: bool,
) -> float:
    """IRL measures market readiness; industries & products add breadth."""
    base = 1.0
    base += min(irl * 1.0, 4.0)
    base += min(industry_count * 0.5, 2.0)
    base += min(product_count * 0.3, 1.5)
    if has_revenue:
        base += 1.5
    return _clamp(base)


def score_team(crl: int) -> float:
    """CRL directly measures team / commercialization readiness."""
    if crl == 0:
        return 3.0  # unknown -> slightly below average
    return _clamp(crl * 10 / 9)


def score_financial(
    revenues: list[float],
    profits: list[float],
) -> float:
    """
    Evaluates financial health from 6 years of data (2020-2025).
    Considers: presence of data, trend, magnitude.
    """
    rev_nonzero = [r for r in revenues if r > 0]
    prof_nonzero = [p for p in profits if p > 0]

    if not rev_nonzero and not prof_nonzero:
        return 2.0  # no data -> low score

    base = 2.0

    # Data availability (max +1)
    data_years = max(len(rev_nonzero), len(prof_nonzero))
    base += min(data_years * 0.2, 1.0)

    # Revenue magnitude (max +3)
    if rev_nonzero:
        max_rev = max(rev_nonzero)
        if max_rev >= 100_000_000:
            base += 3.0
        elif max_rev >= 10_000_000:
            base += 2.0
        elif max_rev >= 1_000_000:
            base += 1.0
        else:
            base += 0.5

    # Profit magnitude (max +2)
    if prof_nonzero:
        max_prof = max(prof_nonzero)
        if max_prof >= 50_000_000:
            base += 2.0
        elif max_prof >= 5_000_000:
            base += 1.5
        elif max_prof >= 500_000:
            base += 1.0
        else:
            base += 0.3

    # Trend (max +2): compare first half vs second half
    if len(rev_nonzero) >= 3:
        mid = len(rev_nonzero) // 2
        first_half = sum(rev_nonzero[:mid]) / mid
        second_half = sum(rev_nonzero[mid:]) / (len(rev_nonzero) - mid)
        if first_half > 0 and second_half / first_half > 1.3:
            base += 2.0
        elif first_half > 0 and second_half / first_half > 1.0:
            base += 1.0

    return _clamp(base)


def compute_overall(
    tech: float,
    innov: float,
    market: float,
    team: float,
    fin: float,
) -> float:
    """Weighted overall score."""
    return _clamp(
        tech * 0.25
        + innov * 0.20
        + market * 0.20
        + team * 0.15
        + fin * 0.20
    )


# ---------------------------------------------------------------------------
# main pipeline
# ---------------------------------------------------------------------------

COLUMN_MAP = {
    "Название компании": "name",
    "Сайт": "website",
    "Описание компании": "company_description",
    "Описание проектов": "description",
    "Описание продуктов": "product_description",
    "TRL (по продуктам)": "trl_raw",
    "IRL - Уровень": "irl_raw",
    "MRL (по продуктам)": "mrl_raw",
    "CRL - Уровень": "crl_raw",
    "Статус организации": "status",
    "Кластер": "cluster",
    "Патенты": "patents",
    "Технологии проекта": "technologies",
    "Отрасли применения": "industries",
    "Названия продуктов": "product_names",
    "Названия проектов": "project_names",
    "ИНН": "inn",
    "ОГРН": "ogrn",
    "Год основания": "year",
    "Выручка 2025": "revenue_2025",
    "Прибыль 2025": "profit_2025",
    "Выручка 2024": "revenue_2024",
    "Прибыль 2024": "profit_2024",
    "Выручка 2023": "revenue_2023",
    "Прибыль 2023": "profit_2023",
    "Выручка 2022": "revenue_2022",
    "Прибыль 2022": "profit_2022",
    "Выручка 2021": "revenue_2021",
    "Прибыль 2021": "profit_2021",
    "Выручка 2020": "revenue_2020",
    "Прибыль 2020": "profit_2020",
}


def label_dataframe(csv_path: str | Path) -> pd.DataFrame:
    """Read CSV, compute proxy scores, return augmented DataFrame."""
    df = pd.read_csv(csv_path, encoding="utf-8", dtype=str)

    for ru, en in COLUMN_MAP.items():
        if ru in df.columns:
            df.rename(columns={ru: en}, inplace=True)

    df["id"] = df["name"].apply(
        lambda x: hashlib.md5(str(x).encode()).hexdigest()
    )
    df.fillna("", inplace=True)

    years = ["2025", "2024", "2023", "2022", "2021", "2020"]

    rows: list[dict] = []
    for _, row in df.iterrows():
        trl = _parse_level(row.get("trl_raw"))
        irl = _parse_level(row.get("irl_raw"))
        mrl = _parse_level(row.get("mrl_raw"))
        crl = _parse_level(row.get("crl_raw"))

        patent_count = _count_patents(row.get("patents"))
        tech_count = _count_items(row.get("technologies"))
        industry_count = _count_items(row.get("industries"))
        product_count = _count_items(row.get("product_names"))

        text = " ".join(
            str(row.get(c, ""))
            for c in [
                "company_description",
                "description",
                "product_description",
                "technologies",
                "product_names",
            ]
        )
        ai_flag = _has_ai(text)

        revenues = [_parse_money(row.get(f"revenue_{y}")) for y in years]
        profits = [_parse_money(row.get(f"profit_{y}")) for y in years]
        has_revenue = any(r > 0 for r in revenues)

        s_tech = score_tech_maturity(trl, irl, mrl, crl)
        s_innov = score_innovation(trl, patent_count, ai_flag, tech_count)
        s_market = score_market_potential(irl, industry_count, product_count, has_revenue)
        s_team = score_team(crl)
        s_fin = score_financial(revenues, profits)
        s_overall = compute_overall(s_tech, s_innov, s_market, s_team, s_fin)

        rows.append(
            {
                "id": row.get("id", ""),
                "name": row.get("name", ""),
                "inn": row.get("inn", ""),
                "cluster": row.get("cluster", ""),
                "status": row.get("status", ""),
                "year": row.get("year", ""),
                "trl": trl,
                "irl": irl,
                "mrl": mrl,
                "crl": crl,
                "patent_count": patent_count,
                "has_ai": int(ai_flag),
                "tech_count": tech_count,
                "industry_count": industry_count,
                "product_count": product_count,
                "max_revenue": max(revenues),
                "max_profit": max(profits),
                "score_tech_maturity": round(s_tech, 2),
                "score_innovation": round(s_innov, 2),
                "score_market_potential": round(s_market, 2),
                "score_team_readiness": round(s_team, 2),
                "score_financial_health": round(s_fin, 2),
                "score_overall": round(s_overall, 2),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Proxy labeler for Skolkovo startups")
    parser.add_argument("--csv", default=str(ROOT / "SkolkovoStartups.csv"))
    parser.add_argument("--out", default=str(ROOT / "scoring" / "labeled_startups.csv"))
    parser.add_argument("--json", action="store_true", help="Also write JSON")
    args = parser.parse_args()

    print(f"Reading {args.csv} ...")
    result = label_dataframe(args.csv)
    result.to_csv(args.out, index=False, encoding="utf-8")
    print(f"Wrote {len(result)} labeled startups -> {args.out}")

    if args.json:
        json_path = args.out.replace(".csv", ".json")
        result.to_json(json_path, orient="records", force_ascii=False, indent=2)
        print(f"Wrote JSON -> {json_path}")

    # quick stats
    print("\n--- Score distribution ---")
    for col in [c for c in result.columns if c.startswith("score_")]:
        print(f"  {col:30s}  mean={result[col].mean():.2f}  min={result[col].min():.2f}  max={result[col].max():.2f}")


if __name__ == "__main__":
    main()
