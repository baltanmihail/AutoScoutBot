"""
Parser for bo.nalog.ru (БФО ФНС) -- Russian financial statements.

Fetches annual financial data: revenue, profit, assets, liabilities.
Uses the open API endpoint that returns JSON by INN.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from .base import BaseParser

logger = logging.getLogger(__name__)


class BFOParser(BaseParser):
    """Fetch financial statements from bo.nalog.ru (open API)."""

    SOURCE_NAME = "bfo"
    # The public endpoint returns JSON for a given INN
    BASE_URL = "https://bo.nalog.ru/nbo/organizations/search"
    REPORTS_URL = "https://bo.nalog.ru/nbo/organizations/{org_id}/bfo"

    async def fetch(self, inn: str) -> Dict[str, Any]:
        client = await self._get_client()

        # Step 1: search for organisation by INN
        resp = await client.get(self.BASE_URL, params={"query": inn, "page": 0})
        resp.raise_for_status()
        search_data = resp.json()

        content = search_data.get("content", [])
        if not content:
            logger.info(f"BFO: организация с ИНН {inn} не найдена")
            return {}

        org = content[0]
        org_id = org.get("id")
        if not org_id:
            return {}

        result = {
            "name": org.get("fullName", ""),
            "inn": org.get("inn", inn),
            "kpp": org.get("kpp", ""),
            "status": org.get("statusName", ""),
            "org_id": org_id,
        }

        # Step 2: fetch financial reports
        try:
            reports_resp = await client.get(self.REPORTS_URL.format(org_id=org_id))
            reports_resp.raise_for_status()
            reports = reports_resp.json()

            yearly_data = {}
            for report in reports if isinstance(reports, list) else []:
                period = report.get("period", {})
                year = period.get("year")
                if not year:
                    continue

                yearly_data[year] = {
                    "revenue": self._extract_value(report, "2110"),
                    "cost_of_sales": self._extract_value(report, "2120"),
                    "gross_profit": self._extract_value(report, "2100"),
                    "net_profit": self._extract_value(report, "2400"),
                    "total_assets": self._extract_value(report, "1600"),
                    "total_liabilities": self._extract_value(report, "1700"),
                    "equity": self._extract_value(report, "1300"),
                    "current_assets": self._extract_value(report, "1200"),
                    "current_liabilities": self._extract_value(report, "1500"),
                }

            result["financials"] = yearly_data

        except Exception as e:
            logger.warning(f"BFO: не удалось получить отчёты для org_id={org_id}: {e}")
            result["financials"] = {}

        return result

    @staticmethod
    def _extract_value(report: dict, line_code: str) -> float:
        """Extract a numeric value from a BFO report by line code."""
        for entry in report.get("data", []):
            if entry.get("code") == line_code:
                try:
                    return float(entry.get("endValue", 0) or 0)
                except (ValueError, TypeError):
                    return 0.0
        return 0.0
