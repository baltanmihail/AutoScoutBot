"""
Parser manager -- orchestrates all external source parsers.

Usage:
    from parsers.manager import ParserManager

    mgr = ParserManager()
    data = await mgr.fetch_all(inn="7707083893", company_name="Сбер")
    # data == {"checko": {...}, "egrul": {...}, "moex": {...}, "news": {...}}
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .checko_parser import CheckoParser
from .egrul_parser import EGRULParser
from .moex_parser import MOEXParser
from .news_parser import NewsParser

logger = logging.getLogger(__name__)


def _get_checko_keys():
    """Возвращает CHECKO_API_KEYS для ротации или одиночный ключ."""
    try:
        from config import CHECKO_API_KEYS
        return CHECKO_API_KEYS
    except Exception:
        try:
            from config import CHECKO_API_KEY
            return CHECKO_API_KEY
        except Exception:
            import os
            return os.environ.get("CHECKO_API_KEY", "")


class ParserManager:
    """Runs all parsers concurrently for a given INN."""

    def __init__(self):
        self.checko = CheckoParser(api_key=_get_checko_keys())
        self.egrul = EGRULParser()
        self.moex = MOEXParser()
        self.news = NewsParser()

    async def fetch_all(
        self,
        inn: str,
        company_name: str = "",
        include: tuple[str, ...] | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch data from all sources in parallel.

        Args:
            inn: Tax identification number.
            company_name: Company name (for news search).
            include: Optional tuple of source names to restrict.
                     Default: all sources.

        Returns:
            Dict mapping source name -> parsed data.
        """
        sources = {
            "checko": self.checko.safe_fetch(inn),
            "egrul": self.egrul.safe_fetch(inn),
            "moex": self.moex.safe_fetch(inn),
            "news": self.news.safe_fetch(inn, company_name=company_name),
        }

        if include:
            sources = {k: v for k, v in sources.items() if k in include}

        results = await asyncio.gather(
            *sources.values(), return_exceptions=True
        )

        output: Dict[str, Dict[str, Any]] = {}
        for source_name, result in zip(sources.keys(), results):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ {source_name}: {result}")
                output[source_name] = {}
            else:
                output[source_name] = result or {}

        filled = sum(1 for v in output.values() if v)
        logger.info(f"📊 ParserManager: {filled}/{len(output)} источников вернули данные для ИНН {inn}")
        return output

    async def close(self):
        """Close all HTTP clients."""
        await asyncio.gather(
            self.checko.close(),
            self.egrul.close(),
            self.moex.close(),
            self.news.close(),
        )
