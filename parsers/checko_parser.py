"""
Parser for Checko.ru -- aggregated financial data.

Checko.ru provides a convenient summary page per INN.
Since there's no official API, this parser scrapes the public HTML page
and extracts key financial indicators.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict

from .base import BaseParser

logger = logging.getLogger(__name__)


class CheckoParser(BaseParser):
    """Scrape Checko.ru for a financial summary by INN."""

    SOURCE_NAME = "checko"
    BASE_URL = "https://checko.ru/company/{inn}"

    async def fetch(self, inn: str) -> Dict[str, Any]:
        client = await self._get_client()

        url = self.BASE_URL.format(inn=inn)
        resp = await client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AutoScoutBot/1.0)"},
        )

        if resp.status_code == 404:
            logger.info(f"Checko: компания с ИНН {inn} не найдена")
            return {}
        resp.raise_for_status()

        html = resp.text
        return self._parse_html(html, inn)

    @staticmethod
    def _parse_html(html: str, inn: str) -> Dict[str, Any]:
        """Extract structured data from Checko.ru HTML."""
        result: Dict[str, Any] = {"inn": inn}

        # Company name
        name_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        if name_match:
            result["name"] = re.sub(r'<[^>]+>', '', name_match.group(1)).strip()

        # Status
        if "Действующая" in html:
            result["status"] = "active"
        elif "Ликвидирована" in html or "Ликвидация" in html:
            result["status"] = "liquidated"
        elif "Реорганизация" in html:
            result["status"] = "reorganized"

        # Revenue (Выручка)
        revenue_match = re.search(
            r'Выручка[^<]*?</[^>]+>[^<]*?<[^>]+>([\d\s,.]+)\s*(тыс|млн|млрд)?',
            html, re.IGNORECASE
        )
        if revenue_match:
            result["revenue"] = _parse_money(revenue_match.group(1), revenue_match.group(2))

        # Profit (Прибыль)
        profit_match = re.search(
            r'Чистая прибыль[^<]*?</[^>]+>[^<]*?<[^>]+>([-\d\s,.]+)\s*(тыс|млн|млрд)?',
            html, re.IGNORECASE
        )
        if profit_match:
            result["net_profit"] = _parse_money(profit_match.group(1), profit_match.group(2))

        # Number of employees
        emp_match = re.search(r'Сотрудники[^<]*?</[^>]+>[^<]*?<[^>]+>(\d+)', html)
        if emp_match:
            try:
                result["employees"] = int(emp_match.group(1))
            except ValueError:
                pass

        # Registration date
        reg_match = re.search(r'Дата регистрации[^<]*?</[^>]+>[^<]*?<[^>]+>(\d{2}\.\d{2}\.\d{4})', html)
        if reg_match:
            result["registration_date"] = reg_match.group(1)

        # Authorized capital
        cap_match = re.search(
            r'Уставный капитал[^<]*?</[^>]+>[^<]*?<[^>]+>([\d\s,.]+)\s*(тыс|млн|млрд)?',
            html, re.IGNORECASE
        )
        if cap_match:
            result["authorized_capital"] = _parse_money(cap_match.group(1), cap_match.group(2))

        return result


def _parse_money(value_str: str, unit: str | None) -> float:
    """Parse a money value string like '12 345,67' with optional unit."""
    try:
        cleaned = value_str.replace(" ", "").replace(",", ".").replace("\xa0", "")
        value = float(cleaned)
        if unit:
            unit = unit.lower().strip()
            if "млрд" in unit:
                value *= 1_000_000_000
            elif "млн" in unit:
                value *= 1_000_000
            elif "тыс" in unit:
                value *= 1_000
        return value
    except (ValueError, TypeError):
        return 0.0
