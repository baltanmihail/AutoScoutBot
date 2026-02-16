"""
Phase 3 -- БФО (Бухгалтерская Финансовая Отчётность) Parser.

Fetches official financial reports from the Russian Federal Tax Service
open data portal: bo.nalog.ru (Бухгалтерская отчётность).

This is the MOST authoritative source for Russian company financials --
data comes directly from ФНС (tax authority) filings.

API endpoint:
    https://bo.nalog.ru/nbo/organizations/{inn}/bfo

Data retrieved:
    - Balance sheet (Бухгалтерский баланс)
    - Profit & Loss statement (Отчёт о финансовых результатах)
    - Key financial indicators: revenue, profit, assets, equity,
      liabilities, current assets, working capital, etc.
    - Multiple years of data (typically 2-3 years per filing)

Source authority: 0.99 (official government data)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ФНС БФО API
BFO_BASE_URL = "https://bo.nalog.ru"
BFO_ORG_URL = f"{BFO_BASE_URL}/nbo/organizations"

RATE_LIMIT_SECONDS = 1.5

HEADERS = {
    "User-Agent": "AutoScoutBot/2.0",
    "Accept": "application/json",
}

# Mapping of BFO line codes to human-readable Russian names
# Based on the official forms (Форма 1 - Баланс, Форма 2 - P&L)
BFO_LINE_NAMES = {
    # Баланс (Form 1)
    "1100": "Внеоборотные активы",
    "1110": "Нематериальные активы",
    "1150": "Основные средства",
    "1170": "Финансовые вложения (долгосрочные)",
    "1200": "Оборотные активы",
    "1210": "Запасы",
    "1230": "Дебиторская задолженность",
    "1250": "Денежные средства",
    "1260": "Прочие оборотные активы",
    "1300": "Капитал и резервы",
    "1310": "Уставный капитал",
    "1370": "Нераспределённая прибыль",
    "1400": "Долгосрочные обязательства",
    "1410": "Заёмные средства (долгосрочные)",
    "1500": "Краткосрочные обязательства",
    "1510": "Заёмные средства (краткосрочные)",
    "1520": "Кредиторская задолженность",
    "1600": "БАЛАНС (актив)",
    "1700": "БАЛАНС (пассив)",
    # P&L (Form 2)
    "2110": "Выручка",
    "2120": "Себестоимость продаж",
    "2100": "Валовая прибыль",
    "2200": "Прибыль от продаж",
    "2300": "Прибыль до налогообложения",
    "2400": "Чистая прибыль",
    "2210": "Коммерческие расходы",
    "2220": "Управленческие расходы",
}


async def fetch_bfo_by_inn(inn: str, timeout: int = 20) -> Optional[dict]:
    """
    Fetch official financial reports from bo.nalog.ru by INN.

    Returns dict with structured financial data across multiple years,
    or None on failure.
    """
    if not inn or not inn.strip():
        return None

    inn = inn.strip()
    if not inn.isdigit() or len(inn) not in (10, 12):
        logger.debug("Invalid INN format for BFO: %s", inn)
        return None

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # Step 1: Get organization info
            org_url = f"{BFO_ORG_URL}?inn={inn}"
            async with session.get(
                org_url,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    logger.debug("BFO org lookup returned %d for INN=%s", resp.status, inn)
                    return None
                org_data = await resp.json()

            org_list = org_data.get("content", [])
            if not org_list:
                logger.debug("No organization found in BFO for INN=%s", inn)
                return None

            org_id = org_list[0].get("id")
            org_name = org_list[0].get("shortName", org_list[0].get("fullName", ""))

            import asyncio
            await asyncio.sleep(RATE_LIMIT_SECONDS)

            # Step 2: Get BFO (financial reports)
            bfo_url = f"{BFO_ORG_URL}/{org_id}/bfo"
            async with session.get(
                bfo_url,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    logger.debug("BFO reports returned %d for org_id=%s", resp.status, org_id)
                    return None
                bfo_data = await resp.json()

        return _parse_bfo_response(bfo_data, inn, org_name)

    except Exception as e:
        logger.error("BFO fetch failed for INN=%s: %s", inn, e)
        return None


def _parse_bfo_response(bfo_data: Any, inn: str, org_name: str) -> Optional[dict]:
    """Parse ФНС BFO API response into structured financial data."""
    if not bfo_data:
        return None

    reports = bfo_data if isinstance(bfo_data, list) else bfo_data.get("content", [])
    if not reports:
        return None

    result = {
        "source": "bfo_fns",
        "fetched_at": datetime.now().isoformat(),
        "inn": inn,
        "org_name": org_name,
        "reports": [],
        "financials_by_year": {},
        "computed_ratios": {},
    }

    for report in reports[:5]:  # Last 5 reports max
        period = report.get("period", {})
        year = period.get("year") or _extract_year(report)

        if not year:
            continue

        report_data = {
            "year": year,
            "period_type": period.get("name", ""),
            "lines": {},
        }

        # Parse balance sheet and P&L lines
        for section in report.get("data", []):
            for line in section.get("lines", []):
                code = str(line.get("code", ""))
                values = line.get("values", [])

                if code in BFO_LINE_NAMES and values:
                    # values[0] = current period, values[1] = previous period
                    current_val = _parse_bfo_value(values[0]) if len(values) > 0 else None
                    prev_val = _parse_bfo_value(values[1]) if len(values) > 1 else None

                    report_data["lines"][code] = {
                        "name": BFO_LINE_NAMES[code],
                        "current": current_val,
                        "previous": prev_val,
                    }

        if report_data["lines"]:
            result["reports"].append(report_data)

            # Build financials_by_year
            yr = str(year)
            fin_year = result["financials_by_year"].setdefault(yr, {})
            for code, vals in report_data["lines"].items():
                if vals["current"] is not None:
                    fin_year[code] = vals["current"]
                    fin_year[f"{code}_name"] = vals["name"]

    # Compute financial ratios from the latest available data
    if result["financials_by_year"]:
        latest_year = max(result["financials_by_year"].keys())
        latest = result["financials_by_year"][latest_year]
        result["computed_ratios"] = _compute_ratios(latest)

    return result if result["reports"] else None


def _compute_ratios(data: dict) -> dict:
    """Compute key financial ratios from BFO line data (тыс. руб.)."""
    ratios = {}

    revenue = data.get("2110", 0) or 0
    cost = data.get("2120", 0) or 0
    gross_profit = data.get("2100", 0) or 0
    net_profit = data.get("2400", 0) or 0
    total_assets = data.get("1600", 0) or 0
    equity = data.get("1300", 0) or 0
    current_assets = data.get("1200", 0) or 0
    current_liabilities = data.get("1500", 0) or 0
    cash = data.get("1250", 0) or 0

    # Profitability
    if revenue > 0:
        ratios["gross_margin"] = round(gross_profit / revenue * 100, 2)
        ratios["net_margin"] = round(net_profit / revenue * 100, 2)

    # Return on Assets (ROA)
    if total_assets > 0:
        ratios["roa"] = round(net_profit / total_assets * 100, 2)

    # Return on Equity (ROE)
    if equity > 0:
        ratios["roe"] = round(net_profit / equity * 100, 2)

    # Current Ratio (liquidity)
    if current_liabilities > 0:
        ratios["current_ratio"] = round(current_assets / current_liabilities, 2)

    # Debt-to-Equity
    total_liabilities = (data.get("1400", 0) or 0) + (data.get("1500", 0) or 0)
    if equity > 0:
        ratios["debt_to_equity"] = round(total_liabilities / equity, 2)

    # Cash ratio
    if current_liabilities > 0:
        ratios["cash_ratio"] = round(cash / current_liabilities, 2)

    # Revenue (in rubles for consistency)
    ratios["revenue_thousands"] = revenue
    ratios["net_profit_thousands"] = net_profit
    ratios["total_assets_thousands"] = total_assets

    return ratios


def _parse_bfo_value(val: Any) -> Optional[float]:
    """Parse a BFO numeric value (usually in thousands of rubles)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        cleaned = str(val).replace(" ", "").replace(",", ".").strip()
        if cleaned in ("", "-", "—"):
            return None
        return float(cleaned)
    except ValueError:
        return None


def _extract_year(report: dict) -> Optional[int]:
    """Try to extract reporting year from report metadata."""
    for key in ("periodYear", "year", "reportYear"):
        val = report.get(key)
        if val and str(val).isdigit():
            y = int(val)
            if 2010 <= y <= 2030:
                return y

    # Try from date fields
    for key in ("periodEnd", "endDate", "date"):
        val = report.get(key, "")
        if val and len(val) >= 4:
            try:
                return int(val[:4])
            except ValueError:
                continue

    return None
