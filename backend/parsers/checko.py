"""
Phase 3 -- Checko.ru / Rusprofile.ru Financial Data Parser.

Scrapes publicly available financial reports (revenue, profit)
from Checko.ru by INN.

Data retrieved:
    - Revenue and profit for recent years
    - Authorized capital
    - Employee count
    - Legal status
    - Industry codes (ОКВЭД)

Note: This uses HTML scraping and may break if the site changes.
Use with appropriate rate limiting.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

CHECKO_URL = "https://checko.ru/company/{inn}"
RUSPROFILE_URL = "https://www.rusprofile.ru/search?query={inn}&type=ul"

# Rate limit: be polite -- max 1 req / 2 sec
RATE_LIMIT_SECONDS = 2.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


async def fetch_financials_by_inn(inn: str, timeout: int = 20) -> Optional[dict]:
    """
    Fetch financial data from Checko.ru by INN.

    Returns dict with financial data, or None on failure.
    """
    if not inn or not inn.strip():
        return None

    inn = inn.strip()
    if not inn.isdigit() or len(inn) not in (10, 12):
        return None

    url = CHECKO_URL.format(inn=inn)

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    logger.debug("Checko returned %d for INN=%s", resp.status, inn)
                    return None
                html = await resp.text()

        return _parse_checko_html(html, inn)

    except Exception as e:
        logger.error("Checko.ru fetch failed for INN=%s: %s", inn, e)
        return None


def _parse_checko_html(html: str, inn: str) -> Optional[dict]:
    """Parse financial data from Checko.ru HTML page."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("beautifulsoup4 not installed, cannot parse Checko.ru HTML")
        return None

    soup = BeautifulSoup(html, "html.parser")

    result = {
        "source": "checko",
        "fetched_at": datetime.now().isoformat(),
        "inn": inn,
        "financials": {},
        "meta": {},
    }

    # Company name
    name_el = soup.find("h1")
    if name_el:
        result["meta"]["company_name"] = name_el.get_text(strip=True)

    # Status
    status_el = soup.find("span", class_=re.compile(r"status"))
    if status_el:
        result["meta"]["status"] = status_el.get_text(strip=True)

    # Try to find financial tables
    # Checko.ru typically shows revenue/profit in tables or specific div blocks
    _extract_financial_table(soup, result)
    _extract_summary_info(soup, result)

    return result if result["financials"] or result["meta"] else None


def _extract_financial_table(soup, result: dict):
    """Try to extract financial data from Checko.ru page tables."""
    # Look for financial summary sections
    fin_sections = soup.find_all("div", class_=re.compile(r"finance|findata|buh"))

    for section in fin_sections:
        rows = section.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            label = cells[0].get_text(strip=True).lower()
            value_text = cells[1].get_text(strip=True)

            if "выручка" in label:
                year = _extract_year_from_text(label)
                val = _parse_financial_value(value_text)
                if year and val is not None:
                    result["financials"][f"revenue_{year}"] = val
            elif "прибыль" in label or "убыток" in label:
                year = _extract_year_from_text(label)
                val = _parse_financial_value(value_text)
                if year and val is not None:
                    result["financials"][f"profit_{year}"] = val

    # Also try to find data in text blocks
    text = soup.get_text()
    for pattern, key_prefix in [
        (r"выручка\s+(?:за\s+)?(\d{4})\s*(?:г\.?)?\s*[:—–-]\s*([\d\s,\.]+)", "revenue"),
        (r"прибыль\s+(?:за\s+)?(\d{4})\s*(?:г\.?)?\s*[:—–-]\s*([\d\s,\.]+)", "profit"),
    ]:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            year = int(m.group(1))
            if 2015 <= year <= 2030:
                val = _parse_financial_value(m.group(2))
                if val is not None:
                    result["financials"][f"{key_prefix}_{year}"] = val


def _extract_summary_info(soup, result: dict):
    """Extract general company info (authorized capital, employees, etc.)."""
    text = soup.get_text()

    # Authorized capital
    m = re.search(r"уставный\s+капитал\s*[:—–-]?\s*([\d\s,\.]+)", text, re.IGNORECASE)
    if m:
        val = _parse_financial_value(m.group(1))
        if val is not None:
            result["meta"]["authorized_capital"] = val

    # Employees
    m = re.search(r"(?:количество|число|численность)\s+(?:сотрудников|работников)\s*[:—–-]?\s*(\d+)", text, re.IGNORECASE)
    if m:
        result["meta"]["employee_count"] = int(m.group(1))

    # Registration date
    m = re.search(r"дата\s+регистрации\s*[:—–-]?\s*(\d{2}\.\d{2}\.\d{4})", text, re.IGNORECASE)
    if m:
        result["meta"]["registration_date"] = m.group(1)


def _extract_year_from_text(text: str) -> Optional[int]:
    """Extract a 4-digit year from text."""
    m = re.search(r"20[12]\d", text)
    if m:
        return int(m.group())
    return None


def _parse_financial_value(text: str) -> Optional[float]:
    """Parse a financial value from text like '123 456 789' or '123,456.78'."""
    if not text:
        return None
    # Remove spaces, replace comma with dot
    cleaned = re.sub(r"[^\d.,\-]", "", text)
    cleaned = cleaned.replace(",", ".")
    # Remove trailing dots
    cleaned = cleaned.rstrip(".")
    if not cleaned or cleaned == "-":
        return None
    try:
        # Handle "тыс. руб." (thousands) multiplier if in original text
        val = float(cleaned)
        if "тыс" in text.lower():
            val *= 1000
        if "млн" in text.lower():
            val *= 1_000_000
        if "млрд" in text.lower():
            val *= 1_000_000_000
        return val
    except ValueError:
        return None
