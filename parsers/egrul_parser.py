"""
Parser for egrul.nalog.ru -- Russian legal entity registry.

Fetches: legal status, registration date, founders, authorised capital.
Uses the public search + PDF download endpoint and parses key fields.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict

from .base import BaseParser

logger = logging.getLogger(__name__)


class EGRULParser(BaseParser):
    """Fetch legal entity information from the EGRUL registry."""

    SOURCE_NAME = "egrul"
    SEARCH_URL = "https://egrul.nalog.ru/"
    RESULT_URL = "https://egrul.nalog.ru/search-result/{token}"

    async def fetch(self, inn: str) -> Dict[str, Any]:
        client = await self._get_client()

        # Step 1: submit search query
        resp = await client.post(
            self.SEARCH_URL,
            data={"query": inn},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("t")
        if not token:
            logger.info(f"EGRUL: поиск по ИНН {inn} не вернул токен")
            return {}

        # Step 2: poll for results (EGRUL uses async processing)
        import asyncio
        for _ in range(10):
            await asyncio.sleep(1)
            result_resp = await client.get(self.RESULT_URL.format(token=token))
            result_resp.raise_for_status()
            result_data = result_resp.json()

            status = result_data.get("status", "")
            if status == "ready":
                rows = result_data.get("rows", [])
                if not rows:
                    return {}

                row = rows[0]
                return self._parse_row(row, inn)

        logger.warning(f"EGRUL: таймаут ожидания результатов для ИНН {inn}")
        return {}

    @staticmethod
    def _parse_row(row: dict, inn: str) -> Dict[str, Any]:
        """Parse a single EGRUL search result row."""
        result: Dict[str, Any] = {
            "inn": inn,
            "ogrn": row.get("o", ""),
            "name": row.get("n", ""),
            "full_name": row.get("c", ""),
            "status": row.get("s", ""),
            "registration_date": row.get("r", ""),
            "address": row.get("a", ""),
        }

        # Extract capital from name/details if available
        capital_match = re.search(r"уставный капитал[:\s]*(\d[\d\s]*)", str(row), re.IGNORECASE)
        if capital_match:
            capital_str = capital_match.group(1).replace(" ", "")
            try:
                result["authorized_capital"] = float(capital_str)
            except ValueError:
                pass

        # Parse status into a boolean flag
        status_lower = result.get("status", "").lower()
        result["is_active"] = "действу" in status_lower or "актив" in status_lower

        return result
