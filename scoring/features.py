"""
Phase 2 -- Feature Engineering.

Extracts a fixed-width numerical feature vector from each startup row.
Used for training XGBoost/LightGBM and for runtime prediction.

Feature groups (total ~30 features):
    Financial   (12) : revenue/profit for 6 years, trends, margins
    Technology  (8)  : TRL, IRL, MRL, CRL, patent count, tech count, AI flag, product count
    Market      (5)  : IRL, industry count, product count, has_revenue, year_founded_age
    Categorical (5)  : cluster (one-hot top-N), status encoded

The module exposes two key functions:
    build_feature_matrix(csv_path)  -> (X: np.ndarray, feature_names: list[str], ids: list[str])
    extract_features(row: dict)     -> np.ndarray   (single row, for runtime prediction)
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from scoring.labeler import _parse_level, _parse_money, _count_patents, _count_items, _has_ai

# Column mapping from Russian CSV headers to English
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

YEARS = ["2025", "2024", "2023", "2022", "2021", "2020"]

# Top clusters for one-hot encoding (covers ~80 % of the data)
TOP_CLUSTERS = [
    "IT-кластер",
    "Биомед",
    "Энерготех",
    "Космос",
    "Ядерные технологии",
]

STATUS_MAP = {
    "Действующий участник": 3,
    "Утвердить статус": 2,
    "Присвоен статус": 2,
    "Выбыл": 0,
    "На рассмотрении": 1,
}


def _safe_log1p(x: float) -> float:
    """log(1 + |x|), preserving sign."""
    if x >= 0:
        return np.log1p(x)
    return -np.log1p(-x)


def _revenue_trend(revenues: list[float]) -> float:
    """Ratio of recent-half sum to older-half sum. >1 means growth."""
    nonzero = [r for r in revenues if r > 0]
    if len(nonzero) < 2:
        return 0.0
    mid = len(nonzero) // 2
    first_half = sum(nonzero[:mid]) or 1.0
    second_half = sum(nonzero[mid:]) or 1.0
    return second_half / first_half


def _profit_margin(revenues: list[float], profits: list[float]) -> float:
    """Average profit margin across years with data."""
    margins = []
    for r, p in zip(revenues, profits):
        if r > 0:
            margins.append(p / r)
    return np.mean(margins) if margins else 0.0


def _years_with_data(values: list[float]) -> int:
    return sum(1 for v in values if v > 0)


def _revenue_stability(revenues: list[float]) -> float:
    """Coefficient of variation (lower = more stable). 0 if <2 data points."""
    nonzero = [r for r in revenues if r > 0]
    if len(nonzero) < 2:
        return 0.0
    arr = np.array(nonzero)
    mean = arr.mean()
    if mean == 0:
        return 0.0
    return float(arr.std() / mean)


def _company_age(year_founded_raw) -> int:
    """Age in years from year founded."""
    try:
        y = int(str(year_founded_raw).strip())
        if 1900 <= y <= 2030:
            return 2026 - y
    except (ValueError, TypeError):
        pass
    return 0


# ---------------------------------------------------------------------------
# Feature names (deterministic order)
# ---------------------------------------------------------------------------

def get_feature_names() -> list[str]:
    """Return ordered list of feature names."""
    names = []

    # Financial features (12)
    for y in YEARS:
        names.append(f"log_revenue_{y}")
    for y in YEARS:
        names.append(f"log_profit_{y}")

    # Financial derived (6)
    names += [
        "max_revenue_log",
        "max_profit_log",
        "revenue_trend",
        "profit_margin",
        "revenue_stability",
        "years_with_revenue",
    ]

    # Technology features (8)
    names += [
        "trl", "irl", "mrl", "crl",
        "patent_count",
        "tech_count",
        "has_ai",
        "product_count",
    ]

    # Market features (4)
    names += [
        "industry_count",
        "project_count",
        "has_revenue",
        "company_age",
    ]

    # Categorical features
    for c in TOP_CLUSTERS:
        names.append(f"cluster_{c}")
    names.append("status_encoded")

    # Text-length proxy features (3)
    names += [
        "len_company_desc",
        "len_product_desc",
        "len_technologies",
    ]

    return names


# ---------------------------------------------------------------------------
# Single-row feature extraction
# ---------------------------------------------------------------------------

def extract_features(row: dict) -> np.ndarray:
    """Extract feature vector from a single startup dict (with English keys)."""
    feats = []

    # Financial: per-year log-revenues and log-profits
    revenues = []
    profits = []
    for y in YEARS:
        rev = _parse_money(row.get(f"revenue_{y}", 0))
        prof = _parse_money(row.get(f"profit_{y}", 0))
        revenues.append(rev)
        profits.append(prof)
        feats.append(_safe_log1p(rev))

    for y in YEARS:
        prof = _parse_money(row.get(f"profit_{y}", 0))
        feats.append(_safe_log1p(prof))

    # Financial derived
    feats.append(_safe_log1p(max(revenues) if revenues else 0))
    feats.append(_safe_log1p(max(profits) if profits else 0))
    feats.append(_revenue_trend(revenues))
    feats.append(_profit_margin(revenues, profits))
    feats.append(_revenue_stability(revenues))
    feats.append(float(_years_with_data(revenues)))

    # Technology features
    trl = _parse_level(row.get("trl_raw", row.get("trl", 0)))
    irl = _parse_level(row.get("irl_raw", row.get("irl", 0)))
    mrl = _parse_level(row.get("mrl_raw", row.get("mrl", 0)))
    crl = _parse_level(row.get("crl_raw", row.get("crl", 0)))
    feats += [float(trl), float(irl), float(mrl), float(crl)]

    patent_count = _count_patents(row.get("patents", ""))
    tech_count = _count_items(row.get("technologies", ""))
    product_count = _count_items(row.get("product_names", ""))

    text_blob = " ".join(
        str(row.get(c, ""))
        for c in ["company_description", "project_description",
                   "product_description", "technologies", "product_names"]
    )
    has_ai_flag = float(_has_ai(text_blob))

    feats += [float(patent_count), float(tech_count), has_ai_flag, float(product_count)]

    # Market features
    industry_count = _count_items(row.get("industries", ""))
    project_count = _count_items(row.get("project_names", ""))
    has_revenue = float(any(r > 0 for r in revenues))
    age = float(_company_age(row.get("year_founded", row.get("year", ""))))

    feats += [float(industry_count), float(project_count), has_revenue, age]

    # Categorical: cluster one-hot
    cluster = str(row.get("cluster", "")).strip()
    for c in TOP_CLUSTERS:
        feats.append(1.0 if cluster == c else 0.0)

    # Status encoded
    status = str(row.get("status", "")).strip()
    feats.append(float(STATUS_MAP.get(status, 1)))

    # Text-length proxies (log-scaled)
    for col in ["company_description", "product_description", "technologies"]:
        feats.append(_safe_log1p(float(len(str(row.get(col, ""))))))

    return np.array(feats, dtype=np.float32)


# ---------------------------------------------------------------------------
# Batch: build full feature matrix from CSV
# ---------------------------------------------------------------------------

def build_feature_matrix(
    csv_path: Union[str, Path],
) -> tuple[np.ndarray, list[str], list[str], np.ndarray]:
    """
    Read CSV, extract features for every startup.

    Returns:
        X             -- (N, D) float32 feature matrix
        feature_names -- list of D feature names
        ids           -- list of N startup IDs (md5 of name)
        y_overall     -- (N,) proxy overall scores (target for training)
    """
    from scoring.labeler import label_dataframe

    df = pd.read_csv(csv_path, encoding="utf-8", dtype=str).fillna("")
    for ru, en in COLUMN_MAP.items():
        if ru in df.columns:
            df.rename(columns={ru: en}, inplace=True)

    df["id"] = df["name"].apply(
        lambda x: hashlib.md5(str(x).encode()).hexdigest()
    )

    # Get proxy labels for targets
    labels_df = label_dataframe(csv_path)
    label_map = {r["id"]: r for _, r in labels_df.iterrows()}

    feature_names = get_feature_names()
    X_list = []
    ids = []
    y_list = []

    for _, row in df.iterrows():
        sid = row["id"]
        feats = extract_features(row.to_dict())
        X_list.append(feats)
        ids.append(sid)

        lbl = label_map.get(sid, {})
        y_overall = float(lbl.get("score_overall", 3.0)) if len(lbl) > 0 else 3.0
        y_list.append(y_overall)

    X = np.vstack(X_list)
    y = np.array(y_list, dtype=np.float32)

    return X, feature_names, ids, y
