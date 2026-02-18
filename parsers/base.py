"""
Base class for all external source parsers.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Abstract base class for external data parsers."""

    SOURCE_NAME: str = "unknown"
    TIMEOUT: int = 30

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.TIMEOUT, follow_redirects=True)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @abstractmethod
    async def fetch(self, inn: str) -> Dict[str, Any]:
        """Fetch data for a startup by INN.

        Returns a dict with source-specific keys, or empty dict on failure.
        """
        ...

    async def safe_fetch(self, inn: str) -> Dict[str, Any]:
        """Wrapper that catches exceptions and returns {} on error."""
        try:
            data = await self.fetch(inn)
            logger.info(f"✅ {self.SOURCE_NAME}: получены данные для ИНН {inn}")
            return data
        except Exception as e:
            logger.warning(f"⚠️ {self.SOURCE_NAME}: ошибка для ИНН {inn}: {e}")
            return {}
