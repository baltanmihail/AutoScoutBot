"""
Phase 3 -- EGRUL / FNS API Parser.

Fetches legal entity data from the Russian Federal Tax Service (ФНС).
Uses the free public API at https://egrul.nalog.ru/ for basic lookups
and the open ФНС API for ОГРН/ИНН queries.

Data retrieved:
    - Legal name, address, registration date
    - Founders / directors
    - Registration status (active / liquidated)
    - ОКВЭД codes (business activity codes)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Public FNS search endpoint (no auth required for basic lookup)
FNS_SEARCH_URL = "https://egrul.nalog.ru/"
FNS_RESULT_URL = "https://egrul.nalog.ru/search-result/"

# Rate limit: max 1 request per second to avoid blocking
RATE_LIMIT_SECONDS = 1.0


async def fetch_egrul_by_inn(inn: str, timeout: int = 15) -> Optional[dict]:
    """
    Query EGRUL by INN (ИНН).

    Returns dict with parsed entity data, or None on failure.
    """
    if not inn or not inn.strip():
        return None

    inn = inn.strip()
    if not inn.isdigit() or len(inn) not in (10, 12):
        logger.warning("Invalid INN format: %s", inn)
        return None

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Submit search request
            payload = {"vyession": inn, "region": "", "page": ""}
            async with session.post(
                FNS_SEARCH_URL,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    logger.warning("FNS search returned %d for INN=%s", resp.status, inn)
                    return None
                result = await resp.json(content_type=None)
                token = result.get("t")

            if not token:
                logger.debug("No search token received for INN=%s", inn)
                return None

            # Step 2: Fetch results
            import asyncio
            await asyncio.sleep(RATE_LIMIT_SECONDS)

            async with session.get(
                f"{FNS_RESULT_URL}{token}",
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)

        return _parse_egrul_response(data, inn)

    except Exception as e:
        logger.error("EGRUL fetch failed for INN=%s: %s", inn, e)
        return None


async def fetch_egrul_by_ogrn(ogrn: str, timeout: int = 15) -> Optional[dict]:
    """Query EGRUL by OGRN (ОГРН)."""
    if not ogrn or not ogrn.strip():
        return None

    ogrn = ogrn.strip()
    if not ogrn.isdigit() or len(ogrn) not in (13, 15):
        logger.warning("Invalid OGRN format: %s", ogrn)
        return None

    try:
        async with aiohttp.ClientSession() as session:
            payload = {"vyession": ogrn, "region": "", "page": ""}
            async with session.post(
                FNS_SEARCH_URL,
                data=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    return None
                result = await resp.json(content_type=None)
                token = result.get("t")

            if not token:
                return None

            import asyncio
            await asyncio.sleep(RATE_LIMIT_SECONDS)

            async with session.get(
                f"{FNS_RESULT_URL}{token}",
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)

        return _parse_egrul_response(data, ogrn)

    except Exception as e:
        logger.error("EGRUL fetch failed for OGRN=%s: %s", ogrn, e)
        return None


def _parse_egrul_response(data: dict, query_id: str) -> Optional[dict]:
    """Extract structured fields from EGRUL API response."""
    if not data:
        return None

    rows = data.get("rows", [])
    if not rows:
        logger.debug("No rows in EGRUL response for %s", query_id)
        return None

    # Take the first (most relevant) result
    entry = rows[0]

    parsed = {
        "source": "egrul",
        "fetched_at": datetime.now().isoformat(),
        "query": query_id,
        "legal_name": entry.get("n", ""),
        "short_name": entry.get("c", ""),
        "inn": entry.get("i", ""),
        "ogrn": entry.get("o", ""),
        "kpp": entry.get("p", ""),
        "registration_date": entry.get("r", ""),
        "address": entry.get("a", ""),
        "status": _parse_status(entry.get("s")),
        "director": entry.get("g", ""),
        "okved_code": entry.get("k", ""),
        "okved_name": entry.get("v", ""),
        "region_code": entry.get("re", ""),
    }

    # Additional fields if available
    if "cnt" in entry:
        parsed["branch_count"] = entry["cnt"]

    return parsed


def _parse_status(status_code) -> str:
    """Convert EGRUL status code to human-readable text."""
    status_map = {
        "1": "Действующее",
        "2": "Ликвидировано",
        "3": "В процессе ликвидации",
        "4": "Реорганизовано",
        "5": "Банкротство",
    }
    if status_code is None:
        return "Неизвестно"
    return status_map.get(str(status_code), str(status_code))
