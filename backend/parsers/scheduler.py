"""
Phase 3 -- Background Scheduler for Data Enrichment.

Runs as a background service inside the FastAPI process.
Uses APScheduler to periodically:
    1. Enrich startup data from EGRUL (by INN/OGRN)
    2. Fetch fresh financial data from Checko.ru (by INN)
    3. Fetch recent news mentions (by company name)

All fetched data is stored in the `external_data` table with
source, timestamp, and authority score.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session
from backend.models import Startup, ExternalData

logger = logging.getLogger(__name__)

# How old external data can be before we re-fetch (days)
REFRESH_INTERVAL_DAYS = {
    "egrul": 30,
    "checko": 14,
    "bfo_fns": 30,     # Official BFO reports update annually
    "moex": 7,         # Market data changes frequently
    "news_ru": 3,      # Russian business news
}

# Max startups to process per scheduler run
BATCH_SIZE = 50


class DataEnrichmentScheduler:
    """Background scheduler for enriching startup data from external sources."""

    def __init__(self):
        self._scheduler = None
        self._running = False

    def start(self, interval_hours: int = 6):
        """Start the APScheduler background jobs."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError:
            logger.warning("apscheduler not installed, background enrichment disabled")
            return

        self._scheduler = AsyncIOScheduler()

        # EGRUL enrichment: every 6 hours
        self._scheduler.add_job(
            self._enrich_egrul_batch,
            IntervalTrigger(hours=interval_hours),
            id="enrich_egrul",
            name="EGRUL data enrichment",
            replace_existing=True,
        )

        # Financial data enrichment: every 12 hours
        self._scheduler.add_job(
            self._enrich_financials_batch,
            IntervalTrigger(hours=interval_hours * 2),
            id="enrich_financials",
            name="Financial data enrichment",
            replace_existing=True,
        )

        # BFO (official financial reports): every 24 hours
        self._scheduler.add_job(
            self._enrich_bfo_batch,
            IntervalTrigger(hours=interval_hours * 4),
            id="enrich_bfo",
            name="BFO financial reports enrichment",
            replace_existing=True,
        )

        # MOEX (market data): every 12 hours
        self._scheduler.add_job(
            self._enrich_moex_batch,
            IntervalTrigger(hours=interval_hours * 2),
            id="enrich_moex",
            name="MOEX market data enrichment",
            replace_existing=True,
        )

        # Russian news (RBC, Interfax, TASS): every 4 hours
        self._scheduler.add_job(
            self._enrich_news_batch,
            IntervalTrigger(hours=max(interval_hours // 2, 2)),
            id="enrich_news",
            name="Russian news enrichment",
            replace_existing=True,
        )

        self._scheduler.start()
        self._running = True
        logger.info("Data enrichment scheduler started (interval=%dh)", interval_hours)

    def stop(self):
        """Stop the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("Data enrichment scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # EGRUL Enrichment
    # ------------------------------------------------------------------

    async def _enrich_egrul_batch(self):
        """Fetch EGRUL data for startups that need it."""
        from backend.parsers.egrul import fetch_egrul_by_inn

        logger.info("Starting EGRUL enrichment batch ...")
        async with async_session() as session:
            startups = await self._get_stale_startups(session, "egrul", BATCH_SIZE)

            enriched = 0
            for startup in startups:
                inn = (startup.inn or "").strip()
                if not inn or not inn.isdigit():
                    continue

                try:
                    data = await fetch_egrul_by_inn(inn)
                    if data:
                        await self._save_external_data(
                            session, startup.id, "egrul", data, authority=0.9
                        )
                        enriched += 1
                except Exception as e:
                    logger.warning("EGRUL enrichment failed for %s: %s", startup.name, e)

                # Rate limiting
                await asyncio.sleep(1.5)

            await session.commit()
            logger.info("EGRUL enrichment complete: %d/%d startups", enriched, len(startups))

    # ------------------------------------------------------------------
    # Financial Enrichment
    # ------------------------------------------------------------------

    async def _enrich_financials_batch(self):
        """Fetch financial data from Checko.ru for startups that need it."""
        from backend.parsers.checko import fetch_financials_by_inn

        logger.info("Starting financial enrichment batch ...")
        async with async_session() as session:
            startups = await self._get_stale_startups(session, "checko", BATCH_SIZE)

            enriched = 0
            for startup in startups:
                inn = (startup.inn or "").strip()
                if not inn or not inn.isdigit():
                    continue

                try:
                    data = await fetch_financials_by_inn(inn)
                    if data:
                        await self._save_external_data(
                            session, startup.id, "checko", data, authority=0.7
                        )
                        enriched += 1
                except Exception as e:
                    logger.warning("Financial enrichment failed for %s: %s", startup.name, e)

                # Rate limiting (Checko is more sensitive)
                await asyncio.sleep(2.5)

            await session.commit()
            logger.info("Financial enrichment complete: %d/%d startups", enriched, len(startups))

    # ------------------------------------------------------------------
    # BFO Enrichment (official financial reports from ФНС)
    # ------------------------------------------------------------------

    async def _enrich_bfo_batch(self):
        """Fetch official BFO financial reports for startups."""
        from backend.parsers.bfo import fetch_bfo_by_inn

        logger.info("Starting BFO enrichment batch ...")
        async with async_session() as session:
            startups = await self._get_stale_startups(session, "bfo_fns", BATCH_SIZE)

            enriched = 0
            for startup in startups:
                inn = (startup.inn or "").strip()
                if not inn or not inn.isdigit():
                    continue

                try:
                    data = await fetch_bfo_by_inn(inn)
                    if data:
                        await self._save_external_data(
                            session, startup.id, "bfo_fns", data, authority=0.99
                        )
                        enriched += 1
                except Exception as e:
                    logger.warning("BFO enrichment failed for %s: %s", startup.name, e)

                await asyncio.sleep(2.0)

            await session.commit()
            logger.info("BFO enrichment complete: %d/%d startups", enriched, len(startups))

    # ------------------------------------------------------------------
    # MOEX Enrichment (market/trading data)
    # ------------------------------------------------------------------

    async def _enrich_moex_batch(self):
        """Fetch MOEX trading data for publicly traded startups."""
        from backend.parsers.moex import search_company_on_moex

        logger.info("Starting MOEX enrichment batch ...")
        async with async_session() as session:
            startups = await self._get_stale_startups(session, "moex", BATCH_SIZE)

            enriched = 0
            for startup in startups:
                name = (startup.name or "").strip()
                inn = (startup.inn or "").strip()
                if not name:
                    continue

                try:
                    data = await search_company_on_moex(name, inn=inn)
                    if data and data.get("securities_found", 0) > 0:
                        await self._save_external_data(
                            session, startup.id, "moex", data, authority=0.99
                        )
                        enriched += 1
                except Exception as e:
                    logger.warning("MOEX enrichment failed for %s: %s", startup.name, e)

                await asyncio.sleep(1.0)

            await session.commit()
            logger.info("MOEX enrichment complete: %d/%d startups", enriched, len(startups))

    # ------------------------------------------------------------------
    # News Enrichment (Russian business media)
    # ------------------------------------------------------------------

    async def _enrich_news_batch(self):
        """Fetch Russian business news for startups."""
        from backend.parsers.news import fetch_news

        logger.info("Starting Russian news enrichment batch ...")
        async with async_session() as session:
            startups = await self._get_stale_startups(session, "news_ru", BATCH_SIZE)

            enriched = 0
            for startup in startups:
                name = (startup.name or "").strip()
                if not name:
                    continue

                try:
                    data = await fetch_news(name)
                    if data:
                        await self._save_external_data(
                            session, startup.id, "news_ru", data, authority=0.75
                        )
                        enriched += 1
                except Exception as e:
                    logger.warning("News enrichment failed for %s: %s", startup.name, e)

                await asyncio.sleep(1.5)

            await session.commit()
            logger.info("Russian news enrichment complete: %d/%d startups", enriched, len(startups))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_stale_startups(
        self,
        session: AsyncSession,
        source: str,
        limit: int,
    ) -> list[Startup]:
        """
        Get startups whose external data from `source` is stale or missing.
        Prioritises startups with higher proxy scores (enrich best startups first).
        """
        from backend.models import StartupScore

        cutoff = datetime.now() - timedelta(days=REFRESH_INTERVAL_DAYS.get(source, 7))

        # Subquery: startup_ids that have fresh data from this source
        fresh_subq = (
            select(ExternalData.startup_id)
            .where(ExternalData.source == source)
            .where(ExternalData.fetched_at >= cutoff)
            .subquery()
        )

        stmt = (
            select(Startup)
            .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
            .where(Startup.id.notin_(select(fresh_subq.c.startup_id)))
            .where(Startup.status != "")
            .order_by(StartupScore.score_overall.desc().nullslast())
            .limit(limit)
        )

        result = (await session.execute(stmt)).scalars().all()
        return list(result)

    async def _save_external_data(
        self,
        session: AsyncSession,
        startup_id: str,
        source: str,
        data: dict,
        authority: float = 0.5,
    ):
        """Save or update external data record."""
        # Check if we already have a record for this source+startup
        stmt = (
            select(ExternalData)
            .where(ExternalData.startup_id == startup_id)
            .where(ExternalData.source == source)
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

        data_json = json.dumps(data, ensure_ascii=False, default=str)

        if existing:
            existing.data_json = data_json
            existing.fetched_at = datetime.now()
            existing.source_authority = authority
        else:
            record = ExternalData(
                startup_id=startup_id,
                source=source,
                source_authority=authority,
                data_json=data_json,
                fetched_at=datetime.now(),
            )
            session.add(record)


# ---------------------------------------------------------------------------
# Manual enrichment functions (for API endpoints)
# ---------------------------------------------------------------------------

async def enrich_single_startup(startup_id: str) -> dict:
    """
    Enrich a single startup from all sources. Useful for on-demand enrichment.

    Returns dict of {source: data_or_error} for each source.
    """
    from backend.parsers.egrul import fetch_egrul_by_inn
    from backend.parsers.checko import fetch_financials_by_inn
    from backend.parsers.bfo import fetch_bfo_by_inn
    from backend.parsers.moex import search_company_on_moex
    from backend.parsers.news import fetch_news

    results = {}

    async with async_session() as session:
        startup = (
            await session.execute(
                select(Startup).where(Startup.id == startup_id)
            )
        ).scalar_one_or_none()

        if not startup:
            return {"error": "Startup not found"}

        scheduler = DataEnrichmentScheduler()
        inn = (startup.inn or "").strip()
        name = (startup.name or "").strip()

        # ЕГРЮЛ (юридический статус)
        if inn and inn.isdigit():
            try:
                data = await fetch_egrul_by_inn(inn)
                if data:
                    await scheduler._save_external_data(session, startup_id, "egrul", data, 0.95)
                    results["egrul"] = data
                else:
                    results["egrul"] = None
            except Exception as e:
                results["egrul"] = {"error": str(e)}

        # БФО ФНС (официальная финансовая отчётность)
        if inn and inn.isdigit():
            try:
                data = await fetch_bfo_by_inn(inn)
                if data:
                    await scheduler._save_external_data(session, startup_id, "bfo_fns", data, 0.99)
                    results["bfo_fns"] = data
                else:
                    results["bfo_fns"] = None
            except Exception as e:
                results["bfo_fns"] = {"error": str(e)}

        # Checko.ru (финансы, дополнительно)
        if inn and inn.isdigit():
            try:
                data = await fetch_financials_by_inn(inn)
                if data:
                    await scheduler._save_external_data(session, startup_id, "checko", data, 0.80)
                    results["checko"] = data
                else:
                    results["checko"] = None
            except Exception as e:
                results["checko"] = {"error": str(e)}

        # MOEX (рыночные данные)
        if name:
            try:
                data = await search_company_on_moex(name, inn=inn)
                if data and data.get("securities_found", 0) > 0:
                    await scheduler._save_external_data(session, startup_id, "moex", data, 0.99)
                    results["moex"] = data
                else:
                    results["moex"] = None
            except Exception as e:
                results["moex"] = {"error": str(e)}

        # Новости (РБК, Интерфакс, ТАСС)
        if name:
            try:
                data = await fetch_news(name)
                if data:
                    await scheduler._save_external_data(session, startup_id, "news_ru", data, 0.75)
                    results["news_ru"] = data
                else:
                    results["news_ru"] = None
            except Exception as e:
                results["news_ru"] = {"error": str(e)}

        await session.commit()

    return results


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_scheduler: Optional[DataEnrichmentScheduler] = None


def get_enrichment_scheduler() -> DataEnrichmentScheduler:
    """Get or create the global scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = DataEnrichmentScheduler()
    return _scheduler
