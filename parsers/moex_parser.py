"""
Parser for MOEX ISS API -- Moscow Exchange market data.

Fetches stock/bond quotes for publicly traded companies.
Only relevant for ~5 % of startups that went public.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from .base import BaseParser

logger = logging.getLogger(__name__)


class MOEXParser(BaseParser):
    """Fetch stock quotes from MOEX ISS API."""

    SOURCE_NAME = "moex"
    SEARCH_URL = "https://iss.moex.com/iss/securities.json"
    QUOTE_URL = "https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}.json"

    async def fetch(self, inn: str, ticker: str = "") -> Dict[str, Any]:
        client = await self._get_client()

        if not ticker:
            # Try to find ticker by INN (search by company name would be better,
            # but we can search by INN as a query).
            resp = await client.get(self.SEARCH_URL, params={"q": inn, "limit": 5})
            resp.raise_for_status()
            data = resp.json()

            securities = data.get("securities", {}).get("data", [])
            columns = data.get("securities", {}).get("columns", [])
            if not securities:
                logger.info(f"MOEX: бумаги по ИНН {inn} не найдены")
                return {}

            # Find ticker column
            try:
                secid_idx = columns.index("secid")
                name_idx = columns.index("shortname") if "shortname" in columns else columns.index("name")
                type_idx = columns.index("type") if "type" in columns else -1
            except ValueError:
                return {}

            # Prefer shares over bonds
            ticker = securities[0][secid_idx]
            for sec in securities:
                if type_idx >= 0 and "share" in str(sec[type_idx]).lower():
                    ticker = sec[secid_idx]
                    break

        if not ticker:
            return {}

        # Fetch quotes
        resp = await client.get(self.QUOTE_URL.format(ticker=ticker))
        resp.raise_for_status()
        quote_data = resp.json()

        marketdata = quote_data.get("marketdata", {})
        md_columns = marketdata.get("columns", [])
        md_data = marketdata.get("data", [])

        if not md_data:
            return {"ticker": ticker, "found": True, "has_quotes": False}

        row = md_data[0]
        result: Dict[str, Any] = {"ticker": ticker, "found": True, "has_quotes": True}

        for col_name in ("LAST", "OPEN", "HIGH", "LOW", "VOLTODAY", "VALTODAY", "MARKETCAP"):
            try:
                idx = md_columns.index(col_name)
                result[col_name.lower()] = row[idx]
            except (ValueError, IndexError):
                pass

        return result
