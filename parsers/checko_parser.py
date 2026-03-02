"""
Parser for Checko.ru Official API v2.

Endpoints used:
  /finances  -- full BFO financial statements by year + basic company info
  /company   -- detailed EGRUL: capital, OKVED, directors, risk factors (optional)

Multi-key rotation: tries keys in order; on 402/403 (limit) switches to next.
  - Old key: 100 req/day free (VK account, no paid)
  - New key: 100 free + 0.15 rub/req after
API docs: https://api.checko.ru/v2
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Union

from .base import BaseParser

logger = logging.getLogger(__name__)

# BFO line codes we care about
BFO_CODES = {
    "2110": "revenue",
    "2120": "cost_of_sales",
    "2100": "gross_profit",
    "2200": "operating_profit",
    "2400": "net_profit",
    "1600": "total_assets",
    "1700": "total_liabilities",
    "1300": "equity",
    "1200": "current_assets",
    "1500": "current_liabilities",
    "1100": "non_current_assets",
    "1150": "fixed_assets",
    "1250": "cash",
    "1370": "retained_earnings",
}


def _normalize_keys(api_key: Optional[Union[str, List[dict]]] = None) -> List[dict]:
    """Convert api_key/CHECKO_API_KEYS to list of {key, label, paid, price_per_request}."""
    if api_key is None:
        api_key = os.environ.get("CHECKO_API_KEY", "")
    if isinstance(api_key, str):
        return [{"key": api_key, "label": "default", "paid": False}] if api_key else []
    if isinstance(api_key, list) and api_key:
        return [
            {
                "key": k.get("key", ""),
                "label": k.get("label", f"key_{i}"),
                "paid": k.get("paid", False),
                "price_per_request": k.get("price_per_request", 0.0),
                "daily_limit": k.get("daily_limit", 100),
            }
            for i, k in enumerate(api_key)
            if k.get("key")
        ]
    return []


class CheckoParser(BaseParser):
    """Fetch data via Checko.ru official API v2. Supports multi-key rotation."""

    SOURCE_NAME = "checko"
    API_BASE = "https://api.checko.ru/v2"

    def __init__(self, api_key: Optional[Union[str, List[dict]]] = None):
        super().__init__()
        self._keys = _normalize_keys(api_key)
        self._paid_requests = 0  # счётчик запросов на платном ключе (для оценки стоимости)
        self._exhausted_key_indices: set[int] = set()  # ключи, у которых сработал лимит в этой сессии

    def get_stats(self) -> Dict[str, Any]:
        """Статистика сессии: сколько запросов на платном ключе, оценка стоимости."""
        return {"paid_requests": self._paid_requests}

    def estimate_paid_cost(self) -> float:
        """Оценка стоимости платных запросов (после 100 бесплатных на платном ключе)."""
        if not self._keys:
            return 0.0
        paid_key = next((k for k in self._keys if k.get("paid")), None)
        if not paid_key:
            return 0.0
        price = paid_key.get("price_per_request", 0.15)
        free = paid_key.get("daily_limit", 100)
        return max(0, self._paid_requests - free) * price

    async def _request(self, endpoint: str, inn: str) -> tuple[Optional[dict], Optional[int]]:
        """Выполнить запрос, перебирая ключи при 402/403. Возвращает (payload, status) или (None, None)."""
        if not self._keys:
            logger.warning("Checko API key not configured, skipping")
            return None, None

        client = await self._get_client()
        last_error = None

        for idx, key_info in enumerate(self._keys):
            if idx in self._exhausted_key_indices:
                continue
            key = key_info["key"]
            label = key_info.get("label", f"key_{idx}")

            resp = await client.get(
                f"{self.API_BASE}/{endpoint}",
                params={"key": key, "inn": inn},
            )

            if resp.status_code in (402, 403):
                logger.info(
                    "Checko: лимит на ключе '%s' (%d), переключаемся на следующий",
                    label, resp.status_code,
                )
                self._exhausted_key_indices.add(idx)
                last_error = resp.status_code
                continue

            if resp.status_code == 404:
                logger.info("Checko: INN %s not found", inn)
                return None, 404

            if resp.status_code != 200:
                resp.raise_for_status()

            if key_info.get("paid"):
                self._paid_requests += 1

            return resp.json(), resp.status_code

        if last_error:
            raise RuntimeError(f"Checko API limit: все ключи исчерпаны (последний: {last_error})")
        return None, None

    async def fetch(self, inn: str) -> Dict[str, Any]:
        if not self._keys:
            logger.warning("Checko API key not configured, skipping")
            return {}

        payload, status = await self._request("finances", inn)
        if payload is None:
            return {} if status == 404 else {}

        result: Dict[str, Any] = {
            "inn": inn,
            "source": "checko_api",
        }

        company_info = payload.get("company", {})
        if company_info:
            self._parse_company_info(company_info, result)

        fin_data = payload.get("data", {})
        result["financials"] = self._parse_financials(fin_data)

        if result["financials"]:
            years = sorted(result["financials"].keys())
            logger.info(
                "Checko API: INN %s — financials for %d years (%s..%s)",
                inn, len(years), years[0], years[-1],
            )

        return result

    @staticmethod
    def _parse_company_info(info: dict, result: dict) -> None:
        """Extract fields from the /finances company block.

        Actual API keys (CamelCase Russian):
          ОГРН, ИНН, КПП, НаимСокр, НаимПолн, ДатаРег, Статус,
          РегионКод, ЮрАдрес, ОКВЭД
        """
        result["name"] = (info.get("\u041d\u0430\u0438\u043c\u041f\u043e\u043b\u043d")
                          or info.get("\u041d\u0430\u0438\u043c\u0421\u043e\u043a\u0440")
                          or "")
        result["short_name"] = info.get("\u041d\u0430\u0438\u043c\u0421\u043e\u043a\u0440", "")
        result["ogrn"] = info.get("\u041e\u0413\u0420\u041d", "")

        created = info.get("\u0414\u0430\u0442\u0430\u0420\u0435\u0433", "")
        if created:
            result["registration_date"] = created
            m = re.search(r"(\d{4})", str(created))
            if m:
                result["year_founded"] = int(m.group(1))

        status_val = info.get("\u0421\u0442\u0430\u0442\u0443\u0441", "")
        if status_val:
            result["status"] = status_val
            result["is_active"] = "\u0434\u0435\u0439\u0441\u0442\u0432" in str(status_val).lower()

        okved = info.get("\u041e\u041a\u0412\u042d\u0414", "")
        if okved:
            result["okved_name"] = okved

        address = info.get("\u042e\u0440\u0410\u0434\u0440\u0435\u0441", "")
        if address:
            result["address"] = address

    @staticmethod
    def _parse_financials(fin_data: dict) -> Dict[int, Dict[str, float]]:
        financials: Dict[int, Dict[str, float]] = {}

        for year_str, year_data in fin_data.items():
            if not isinstance(year_data, dict):
                continue
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            if year < 2015 or year > 2030:
                continue

            year_parsed: Dict[str, float] = {}
            for code, name in BFO_CODES.items():
                val = year_data.get(code, 0)
                if val:
                    try:
                        year_parsed[name] = float(val)
                    except (ValueError, TypeError):
                        pass

            if year_parsed:
                financials[year] = year_parsed

        return financials

    async def fetch_company(self, inn: str) -> Dict[str, Any]:
        """Detailed company info (EGRUL, capital, OKVED, etc). Extra API request."""
        if not self._keys:
            return {}
        payload, _ = await self._request("company", inn)
        if payload is None:
            return {}
        return payload.get("data", {})
