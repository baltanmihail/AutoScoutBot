"""
Phase 3 -- MOEX (Moscow Exchange) Parser.

Fetches stock/bond trading data for publicly traded companies
from the MOEX ISS (Information & Statistical Server) open API.

API docs: https://iss.moex.com/iss/reference/
No authentication required. JSON/XML endpoints.

Data retrieved:
    - Current market price and volume
    - Historical price data (for trend analysis)
    - Bond listings and yields (if any)
    - Market capitalization estimate

Source authority: 0.99 (official exchange data)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

MOEX_ISS_BASE = "https://iss.moex.com/iss"

HEADERS = {
    "User-Agent": "AutoScoutBot/2.0",
    "Accept": "application/json",
}

RATE_LIMIT_SECONDS = 0.5


async def search_company_on_moex(
    company_name: str, inn: str = "", timeout: int = 15
) -> Optional[dict]:
    """
    Search for a company on MOEX by name or INN.

    Returns dict with security info and trading data, or None if not found.
    """
    if not company_name and not inn:
        return None

    # Try searching by company name first
    query = inn if inn else company_name.strip()

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # Step 1: Search for securities
            search_url = f"{MOEX_ISS_BASE}/securities.json"
            params = {"q": query, "limit": 5, "is_trading": 1}

            async with session.get(
                search_url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

            securities = _parse_securities_search(data)
            if not securities:
                # Try with shortened name
                if len(query) > 5 and not inn:
                    short_query = query[:min(len(query), 10)]
                    params["q"] = short_query
                    async with session.get(
                        search_url, params=params,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            securities = _parse_securities_search(data)

                if not securities:
                    return None

            # Step 2: Get market data for the first (best) match
            best_sec = securities[0]
            sec_id = best_sec["secid"]
            engine = best_sec.get("engine", "stock")
            market = best_sec.get("market", "shares")
            board = best_sec.get("primary_boardid", "TQBR")

            import asyncio
            await asyncio.sleep(RATE_LIMIT_SECONDS)

            # Get current market data
            market_url = (
                f"{MOEX_ISS_BASE}/engines/{engine}/markets/{market}"
                f"/boards/{board}/securities/{sec_id}.json"
            )
            async with session.get(
                market_url,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 200:
                    market_data = await resp.json()
                    best_sec["market_data"] = _parse_market_data(market_data)

            await asyncio.sleep(RATE_LIMIT_SECONDS)

            # Get historical data (last 30 days)
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            history_url = (
                f"{MOEX_ISS_BASE}/history/engines/{engine}/markets/{market}"
                f"/boards/{board}/securities/{sec_id}.json"
            )
            async with session.get(
                history_url,
                params={"from": date_from, "limit": 30},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 200:
                    history_data = await resp.json()
                    best_sec["history"] = _parse_history(history_data)

        return {
            "source": "moex",
            "fetched_at": datetime.now().isoformat(),
            "company_name": company_name,
            "securities_found": len(securities),
            "primary_security": best_sec,
            "all_securities": securities[:3],
        }

    except Exception as e:
        logger.error("MOEX fetch failed for '%s': %s", company_name, e)
        return None


def _parse_securities_search(data: dict) -> list[dict]:
    """Parse MOEX ISS securities search response."""
    results = []

    securities = data.get("securities", {})
    columns = securities.get("columns", [])
    rows = securities.get("data", [])

    for row in rows:
        entry = dict(zip(columns, row))
        results.append({
            "secid": entry.get("secid", ""),
            "shortname": entry.get("shortname", ""),
            "name": entry.get("name", ""),
            "isin": entry.get("isin", ""),
            "type": entry.get("type", ""),
            "engine": entry.get("group", "stock").split("_")[0] if entry.get("group") else "stock",
            "market": _infer_market(entry.get("type", "")),
            "primary_boardid": entry.get("primary_boardid", "TQBR"),
        })

    return results


def _parse_market_data(data: dict) -> dict:
    """Parse current market data from MOEX ISS."""
    result = {}

    for section_name in ("marketdata", "securities"):
        section = data.get(section_name, {})
        columns = section.get("columns", [])
        rows = section.get("data", [])

        if rows:
            entry = dict(zip(columns, rows[0]))
            result.update({
                k: v for k, v in entry.items()
                if v is not None and k in (
                    "LAST", "OPEN", "HIGH", "LOW", "VOLTODAY", "VALTODAY",
                    "MARKETPRICE", "CLOSEPRICE", "PREVPRICE", "CHANGE",
                    "FACEVALUE", "LOTSIZE", "SECNAME", "PREVDATE",
                    "ISSUECAPITALIZATION", "LISTLEVEL",
                )
            })

    return result


def _parse_history(data: dict) -> list[dict]:
    """Parse historical trading data."""
    history_section = data.get("history", {})
    columns = history_section.get("columns", [])
    rows = history_section.get("data", [])

    result = []
    for row in rows:
        entry = dict(zip(columns, row))
        result.append({
            "date": entry.get("TRADEDATE", ""),
            "close": entry.get("CLOSE") or entry.get("LEGALCLOSEPRICE"),
            "volume": entry.get("VOLUME"),
            "value": entry.get("VALUE"),
            "high": entry.get("HIGH"),
            "low": entry.get("LOW"),
        })

    return result


def _infer_market(security_type: str) -> str:
    """Infer MOEX market from security type."""
    t = security_type.lower()
    if "bond" in t or "облигац" in t:
        return "bonds"
    if "share" in t or "акци" in t:
        return "shares"
    return "shares"
