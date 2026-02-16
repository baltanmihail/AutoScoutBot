"""
Phase 3 -- Russian Business News Parser (RBC, Interfax, TASS).

Fetches recent news mentions for a startup from Russian business media
RSS feeds. Replaces the previous Google News parser which was poorly
suited for the Russian startup market.

Sources:
    - RBC.ru (rbc.ru/rssfeeds)     -- top Russian business news
    - Interfax (interfax.ru/rss)   -- financial & corporate news
    - TASS (tass.ru/rss)           -- state news agency (tech & innovation)

Data retrieved:
    - List of recent news articles (title, link, published date, source)
    - Mention count
    - Sentiment hint (positive/negative keyword scan)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import aiohttp

logger = logging.getLogger(__name__)

# Russian business RSS feeds
RSS_FEEDS = {
    "rbc_business": {
        "url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
        "name": "РБК",
        "authority": 0.85,
    },
    "rbc_tech": {
        "url": "https://rssexport.rbc.ru/rbcnews/news/topic/26/full.rss",
        "name": "РБК Технологии",
        "authority": 0.85,
    },
    "interfax": {
        "url": "https://www.interfax.ru/rss.asp",
        "name": "Интерфакс",
        "authority": 0.90,
    },
    "tass_economy": {
        "url": "https://tass.ru/rss/v2.xml",
        "name": "ТАСС",
        "authority": 0.90,
    },
}

POSITIVE_KEYWORDS = {
    "инвестиции", "рост", "успех", "сделка", "партнерство", "запуск",
    "выход", "прибыль", "достижение", "победа", "грант", "ipo",
    "экспансия", "расширение", "контракт", "патент", "награда",
    "привлек", "раунд", "финансирование", "акселератор", "резидент",
}

NEGATIVE_KEYWORDS = {
    "убыток", "банкротство", "ликвидация", "скандал", "увольнение",
    "потеря", "штраф", "суд", "иск", "долг", "кризис",
    "закрытие", "проблемы", "провал", "банкрот",
}

RATE_LIMIT_SECONDS = 1.0


async def fetch_news(
    company_name: str,
    max_items: int = 15,
    timeout: int = 15,
) -> Optional[dict]:
    """
    Fetch recent news about a company from Russian business media RSS feeds.

    Searches across RBC, Interfax, TASS for mentions of the company name.
    Returns dict with news articles and metadata, or None on failure.
    """
    if not company_name or not company_name.strip():
        return None

    company_name = company_name.strip()
    # Normalize: remove legal form prefixes for better matching
    search_name = re.sub(
        r"^(ООО|ОАО|ЗАО|ПАО|АО|НКО|ИП)\s+", "", company_name, flags=re.IGNORECASE
    ).strip('"«»" ')

    if len(search_name) < 3:
        return None

    all_articles = []

    try:
        async with aiohttp.ClientSession() as session:
            for feed_id, feed_info in RSS_FEEDS.items():
                try:
                    async with session.get(
                        feed_info["url"],
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        headers={"User-Agent": "AutoScoutBot/2.0"},
                    ) as resp:
                        if resp.status != 200:
                            continue
                        xml_text = await resp.text()

                    articles = _search_in_rss(xml_text, search_name, feed_info["name"])
                    all_articles.extend(articles)

                except Exception as e:
                    logger.debug("Feed %s failed: %s", feed_id, e)

                import asyncio
                await asyncio.sleep(RATE_LIMIT_SECONDS)

    except Exception as e:
        logger.error("News fetch failed for '%s': %s", company_name, e)
        return None

    if not all_articles:
        return None

    # Deduplicate by title similarity and limit
    unique_articles = _deduplicate(all_articles)[:max_items]

    # Sentiment analysis
    all_titles = " ".join(a["title"].lower() for a in unique_articles)
    positive_hits = sum(1 for kw in POSITIVE_KEYWORDS if kw in all_titles)
    negative_hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw in all_titles)

    sentiment = "neutral"
    if positive_hits > negative_hits + 1:
        sentiment = "positive"
    elif negative_hits > positive_hits + 1:
        sentiment = "negative"

    return {
        "source": "news_ru",
        "fetched_at": datetime.now().isoformat(),
        "company_name": company_name,
        "article_count": len(unique_articles),
        "articles": unique_articles,
        "sentiment": sentiment,
        "positive_signals": positive_hits,
        "negative_signals": negative_hits,
    }


def _search_in_rss(xml_text: str, search_name: str, source_name: str) -> list[dict]:
    """Search for company mentions in RSS XML content."""
    articles = []
    search_lower = search_name.lower()

    # Parse items using regex (works without feedparser dependency)
    item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
    title_pattern = re.compile(r"<title>(.*?)</title>", re.DOTALL)
    link_pattern = re.compile(r"<link>(.*?)</link>")
    pubdate_pattern = re.compile(r"<pubDate>(.*?)</pubDate>")
    desc_pattern = re.compile(r"<description>(.*?)</description>", re.DOTALL)

    for match in item_pattern.finditer(xml_text):
        item_xml = match.group(1)

        title_m = title_pattern.search(item_xml)
        title = _clean_xml_text(title_m.group(1)) if title_m else ""

        desc_m = desc_pattern.search(item_xml)
        desc = _clean_xml_text(desc_m.group(1)) if desc_m else ""

        # Check if company is mentioned in title or description
        combined = (title + " " + desc).lower()
        if search_lower not in combined:
            continue

        link_m = link_pattern.search(item_xml)
        pubdate_m = pubdate_pattern.search(item_xml)

        articles.append({
            "title": title,
            "link": link_m.group(1) if link_m else "",
            "published": pubdate_m.group(1) if pubdate_m else "",
            "source": source_name,
        })

    return articles


def _deduplicate(articles: list[dict]) -> list[dict]:
    """Remove near-duplicate articles by title."""
    seen_titles = set()
    unique = []
    for a in articles:
        # Normalize title for comparison
        norm_title = re.sub(r"\s+", " ", a["title"].lower().strip())
        if norm_title not in seen_titles:
            seen_titles.add(norm_title)
            unique.append(a)
    return unique


def _clean_xml_text(text: str) -> str:
    """Remove CDATA wrappers, HTML tags and XML entities."""
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&apos;", "'")
    return text.strip()
