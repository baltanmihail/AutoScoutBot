"""
API Client -- Thin HTTP client for the bot to call the FastAPI backend.

The bot becomes a "thin client" that delegates search, scoring, and
enrichment to the backend API server.

Configuration:
    BACKEND_URL env var or fallback to http://localhost:8000
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
TIMEOUT = 30.0


class AutoScoutAPI:
    """Async HTTP client for the AutoScoutBot FastAPI backend."""

    def __init__(self, base_url: str = BACKEND_URL):
        self._base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=TIMEOUT,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health(self) -> dict:
        """Check if the backend is alive."""
        client = await self._get_client()
        try:
            resp = await client.get("/health")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Backend health check failed: %s", e)
            return {"status": "unavailable", "error": str(e)}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        model_type: str = "standard",
        top_k: int = 5,
        filters: dict | None = None,
        user_id: int | None = None,
    ) -> Optional[dict]:
        """
        Call /search endpoint.

        Returns SearchResponse dict or None on error.
        """
        client = await self._get_client()
        payload = {
            "query": query,
            "model_type": model_type,
            "top_k": top_k,
            "filters": filters or {},
            "user_id": user_id,
        }

        try:
            resp = await client.post("/search/", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Search API error %d: %s", e.response.status_code, e.response.text)
            return None
        except Exception as e:
            logger.error("Search API call failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    async def get_score(self, startup_id: str) -> Optional[dict]:
        """
        Call /score endpoint for basic scores + SHAP.
        """
        client = await self._get_client()
        try:
            resp = await client.post("/score/", json={"startup_id": startup_id})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Score API call failed for %s: %s", startup_id, e)
            return None

    async def get_full_score(self, startup_id: str) -> Optional[dict]:
        """
        Call /score/full endpoint for complete scoring pipeline.
        """
        client = await self._get_client()
        try:
            resp = await client.post("/score/full", json={"startup_id": startup_id})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Full score API call failed for %s: %s", startup_id, e)
            return None

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    async def get_stats(self) -> Optional[dict]:
        """Call /admin/stats endpoint."""
        client = await self._get_client()
        try:
            resp = await client.get("/admin/stats")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Stats API call failed: %s", e)
            return None

    async def get_enrichment_status(self) -> Optional[dict]:
        """Call /admin/enrichment/status endpoint."""
        client = await self._get_client()
        try:
            resp = await client.get("/admin/enrichment/status")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Enrichment status API call failed: %s", e)
            return None

    async def enrich_startup(self, startup_id: str) -> Optional[dict]:
        """Call /admin/enrich/{startup_id} endpoint."""
        client = await self._get_client()
        try:
            resp = await client.post(f"/admin/enrich/{startup_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Enrich API call failed for %s: %s", startup_id, e)
            return None

    async def get_ml_status(self) -> Optional[dict]:
        """Call /admin/ml/status endpoint."""
        client = await self._get_client()
        try:
            resp = await client.get("/admin/ml/status")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("ML status API call failed: %s", e)
            return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_api_client: Optional[AutoScoutAPI] = None


def get_api_client() -> AutoScoutAPI:
    """Get or create the global API client singleton."""
    global _api_client
    if _api_client is None:
        _api_client = AutoScoutAPI()
    return _api_client
