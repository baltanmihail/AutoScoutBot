"""
Parser for Russian news RSS feeds (RBC, TASS, Interfax).

Searches for startup mentions in recent news articles and returns
headline + link + publication date.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List

from .base import BaseParser

logger = logging.getLogger(__name__)


RSS_FEEDS = {
    "rbc": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "tass": "https://tass.ru/rss/v2.xml",
    "interfax": "https://www.interfax.ru/rss.asp",
}


class NewsParser(BaseParser):
    """Search for startup mentions in Russian news RSS feeds."""

    SOURCE_NAME = "news"

    async def fetch(self, inn: str, company_name: str = "") -> Dict[str, Any]:
        """Fetch news mentions for a company.

        Args:
            inn: Tax ID (used as fallback search term).
            company_name: Company name to search for (preferred).

        Returns:
            Dict with keys: mentions (list), total_count (int).
        """
        if not company_name:
            return {"mentions": [], "total_count": 0}

        search_terms = self._build_search_terms(company_name)
        client = await self._get_client()

        all_mentions: List[Dict[str, Any]] = []

        for feed_name, feed_url in RSS_FEEDS.items():
            try:
                resp = await client.get(feed_url, timeout=15)
                if resp.status_code != 200:
                    continue

                mentions = self._search_feed(resp.text, search_terms, feed_name)
                all_mentions.extend(mentions)

            except Exception as e:
                logger.warning(f"News: ошибка парсинга {feed_name}: {e}")

        # Sort by date (newest first) and limit
        all_mentions.sort(key=lambda m: m.get("date", ""), reverse=True)

        return {
            "mentions": all_mentions[:20],
            "total_count": len(all_mentions),
        }

    @staticmethod
    def _build_search_terms(company_name: str) -> List[str]:
        """Build search term variants from company name."""
        terms = [company_name.lower()]
        # Add short name (first two meaningful words)
        words = [w for w in company_name.split() if len(w) > 3]
        if len(words) >= 2:
            terms.append(" ".join(words[:2]).lower())
        if words:
            terms.append(words[0].lower())
        return terms

    @staticmethod
    def _search_feed(xml_text: str, search_terms: List[str], source: str) -> List[Dict[str, Any]]:
        """Parse RSS XML and find matching items."""
        mentions = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return mentions

        # Handle RSS 2.0 and Atom formats
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for item in items:
            title_el = item.find("title") or item.find("{http://www.w3.org/2005/Atom}title")
            desc_el = item.find("description") or item.find("{http://www.w3.org/2005/Atom}summary")
            link_el = item.find("link") or item.find("{http://www.w3.org/2005/Atom}link")
            date_el = item.find("pubDate") or item.find("{http://www.w3.org/2005/Atom}published")

            title = (title_el.text or "") if title_el is not None else ""
            description = (desc_el.text or "") if desc_el is not None else ""
            link = ""
            if link_el is not None:
                link = link_el.text or link_el.get("href", "")
            pub_date = (date_el.text or "") if date_el is not None else ""

            text_to_search = (title + " " + description).lower()
            text_to_search = re.sub(r"<[^>]+>", "", text_to_search)  # strip HTML tags

            for term in search_terms:
                if term in text_to_search:
                    mentions.append({
                        "source": source,
                        "title": title.strip(),
                        "link": link.strip(),
                        "date": pub_date.strip(),
                        "matched_term": term,
                    })
                    break

        return mentions
