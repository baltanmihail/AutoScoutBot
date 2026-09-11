"""Calibrated fusion of query relevance and query-independent attractiveness for search ranking.

The raw linear rule  lam*rel + (1-lam)*attr  orders candidates exactly as the standardized rule with
relevance weight  omega = lam*sd_rel / (lam*sd_rel + (1-lam)*sd_attr).  With rel = 10*cosine the relevance
spread among candidates is ~3x smaller than the attractiveness spread, so the nominal 0.5 acted as ~0.25 and
the top positions drifted to mature companies (PIERE 2026 study, docs/Статьи/Scopus, IEEE, ВАК).
Standardizing both signals on the candidate set makes the configured weight the effective one; attractiveness
is compared within the company's stage (TRL group) via an empirical CDF built on the whole corpus.
"""

from __future__ import annotations

import bisect
import math
from typing import Iterable, Optional

STAGE_BINS = ((1, 3, "trl_1_3"), (4, 6, "trl_4_6"), (7, 9, "trl_7_9"))


def stage_of(trl) -> str:
    """TRL group of a company; missing or zero TRL is a separate group."""
    try:
        t = int(float(trl or 0))
    except (TypeError, ValueError):
        return "unknown"
    for lo, hi, name in STAGE_BINS:
        if lo <= t <= hi:
            return name
    return "unknown"


class StagePercentiles:
    """Empirical CDF of the attractiveness score within each stage group."""

    def __init__(self, rows: Iterable[tuple]):
        groups: dict[str, list[float]] = {}
        for trl, score in rows:
            if score is not None:
                groups.setdefault(stage_of(trl), []).append(float(score))
        self._sorted = {g: sorted(v) for g, v in groups.items()}

    def percentile(self, trl, score: Optional[float]) -> float:
        vals = self._sorted.get(stage_of(trl))
        if not vals or score is None:
            return 0.5
        return bisect.bisect_right(vals, float(score)) / len(vals)


def zscores(xs: list[float]) -> list[float]:
    n = len(xs)
    if n == 0:
        return []
    mean = sum(xs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / n)
    if sd < 1e-12:
        return [0.0] * n
    return [(x - mean) / sd for x in xs]


def calibrated_scores(rel: list[float], attr: list[float], omega: float = 0.5) -> tuple[list[float], list[float]]:
    """Fused score (sort key) and a 0..10 display value, 10*Phi(standardized fused), monotone in the fused score."""
    fused = [omega * r + (1.0 - omega) * a for r, a in zip(zscores(rel), zscores(attr))]
    display = [5.0 * (1.0 + math.erf(f / math.sqrt(2.0))) for f in zscores(fused)]
    return fused, display


def effective_relevance_weight(rel: list[float], attr: list[float], lam: float) -> float:
    """Effective relevance weight of the raw rule lam*rel + (1-lam)*attr on this candidate set."""
    def sd(xs):
        m = sum(xs) / len(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
    if len(rel) < 2:
        return lam
    wr, wa = lam * sd(rel), (1.0 - lam) * sd(attr)
    return wr / (wr + wa) if wr + wa > 0 else lam
