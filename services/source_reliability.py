"""
Source reliability engine.

Computes reliability scores for each external data source by cross-referencing
their data against the Skolkovo ground truth for startups that appear in both.

Algorithm:
  For each source S:
    1. Find startups that exist in both Skolkovo CSV and source S (overlap set).
    2. Compare numeric fields (revenue, profit, registration year, etc.).
    3. reliability(S, field) = 1 - mean_normalized_error(S_data, skolkovo_data)
    4. Store results in source_reliability table.

Usage:
    from services.source_reliability import ReliabilityEngine
    engine = ReliabilityEngine(skolkovo_db)
    await engine.compute_all()
    print(engine.get_reliability("bfo", "revenue"))  # -> 0.92
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReliabilityEngine:
    """Compute and cache source reliability scores."""

    def __init__(self, skolkovo_db: List[Dict[str, Any]]):
        self._skolkovo = skolkovo_db or []
        self._inn_index: Dict[str, Dict[str, Any]] = {}
        self._scores: Dict[str, Dict[str, float]] = {}  # {source: {field: reliability}}
        self._build_inn_index()

    def _build_inn_index(self):
        """Build a lookup from INN -> Skolkovo startup dict."""
        for startup in self._skolkovo:
            inn = str(startup.get("inn", "")).strip()
            if inn and len(inn) >= 10:
                self._inn_index[inn] = startup
        logger.info(f"ReliabilityEngine: indexed {len(self._inn_index)} startups by INN")

    async def compute_for_source(
        self,
        source_name: str,
        external_data_by_inn: Dict[str, Dict[str, Any]],
    ) -> Dict[str, float]:
        """Compute reliability for one source by comparing with ground truth.

        Args:
            source_name: e.g. "bfo", "checko", "egrul"
            external_data_by_inn: dict mapping INN -> data from this source.

        Returns:
            Dict mapping field_name -> reliability (0.0 to 1.0).
        """
        field_errors: Dict[str, List[float]] = {}

        for inn, ext_data in external_data_by_inn.items():
            skolkovo = self._inn_index.get(inn)
            if not skolkovo:
                continue

            # Compare revenue fields
            comparisons = self._get_field_comparisons(skolkovo, ext_data, source_name)
            for field_name, (truth, external) in comparisons.items():
                if truth is None or external is None:
                    continue
                if truth == 0 and external == 0:
                    error = 0.0
                elif truth == 0:
                    error = 1.0
                else:
                    error = min(1.0, abs(truth - external) / (abs(truth) + 1e-9))

                field_errors.setdefault(field_name, []).append(error)

        # Compute reliability = 1 - mean_error
        reliability: Dict[str, float] = {}
        for field, errors in field_errors.items():
            if errors:
                mean_err = sum(errors) / len(errors)
                reliability[field] = round(1.0 - mean_err, 4)
                logger.info(
                    f"  {source_name}/{field}: reliability={reliability[field]:.3f} "
                    f"(samples={len(errors)})"
                )

        # Overall reliability (average of all fields)
        if reliability:
            reliability["overall"] = round(
                sum(reliability.values()) / len(reliability), 4
            )

        self._scores[source_name] = reliability
        return reliability

    def get_reliability(self, source: str, field: str = "overall") -> float:
        """Get cached reliability score for a source/field pair."""
        return self._scores.get(source, {}).get(field, 0.5)

    def get_all_scores(self) -> Dict[str, Dict[str, float]]:
        """Get all computed reliability scores."""
        return self._scores

    @staticmethod
    def _get_field_comparisons(
        skolkovo: Dict[str, Any],
        external: Dict[str, Any],
        source: str,
    ) -> Dict[str, tuple]:
        """Map ground truth fields to external data fields for comparison."""
        comparisons: Dict[str, tuple] = {}

        if source in ("bfo", "checko"):
            # Revenue comparison (latest available year)
            for year in range(2025, 2019, -1):
                sk_rev = _safe_float(skolkovo.get(f"revenue_{year}"))
                ext_financials = external.get("financials", {})
                ext_year = ext_financials.get(year, ext_financials.get(str(year), {}))
                ext_rev = ext_year.get("revenue") if isinstance(ext_year, dict) else None
                if ext_rev is None and source == "checko":
                    ext_rev = _safe_float(external.get("revenue"))
                if sk_rev is not None and ext_rev is not None:
                    comparisons[f"revenue_{year}"] = (sk_rev, ext_rev)

            # Profit comparison
            for year in range(2025, 2019, -1):
                sk_prof = _safe_float(skolkovo.get(f"profit_{year}"))
                ext_financials = external.get("financials", {})
                ext_year = ext_financials.get(year, ext_financials.get(str(year), {}))
                ext_prof = ext_year.get("net_profit") if isinstance(ext_year, dict) else None
                if ext_prof is None and source == "checko":
                    ext_prof = _safe_float(external.get("net_profit"))
                if sk_prof is not None and ext_prof is not None:
                    comparisons[f"profit_{year}"] = (sk_prof, ext_prof)

        if source == "egrul":
            # Registration year
            sk_year = _safe_float(skolkovo.get("year"))
            ext_date = external.get("registration_date", "")
            import re
            year_match = re.search(r"(\d{4})", str(ext_date))
            if sk_year and year_match:
                comparisons["year_founded"] = (sk_year, float(year_match.group(1)))

            # Active status
            sk_status = str(skolkovo.get("status", "")).lower()
            sk_active = 1.0 if "activ" in sk_status or "действ" in sk_status else 0.0
            ext_active = 1.0 if external.get("is_active") else 0.0
            comparisons["is_active"] = (sk_active, ext_active)

        return comparisons


def _safe_float(val) -> Optional[float]:
    """Convert value to float, return None if impossible."""
    if val is None or val == "" or val == "н/д":
        return None
    try:
        f = float(val)
        return f if not math.isnan(f) else None
    except (ValueError, TypeError):
        return None
