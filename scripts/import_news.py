import asyncio
import logging
import json
import httpx
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import sys
from pathlib import Path

# Add project root to python path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from sqlalchemy import select
from backend.database import async_session
from backend.models import Startup, ExternalData

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def fetch_google_news(client: httpx.AsyncClient, query: str, max_results: int = 5) -> list:
    """Fetch latest news from Google News RSS in Russian."""
    # Ensure we get Russian news
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ru&gl=RU&ceid=RU:ru"
    
    try:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(response.text)
        channel = root.find("channel")
        
        news_items = []
        if channel is not None:
            for item in channel.findall("item")[:max_results]:
                title = item.findtext("title")
                link = item.findtext("link")
                pub_date = item.findtext("pubDate")
                source = item.findtext("source")
                
                news_items.append({
                    "title": title,
                    "link": link,
                    "published_at": pub_date,
                    "source": source
                })
                
        return news_items
    except Exception as e:
        logger.debug(f"Failed to fetch news for query '{query}': {e}")
        return []

async def process_batch():
    async with async_session() as session:
        # Get all startups
        stmt = select(Startup.id, Startup.name, Startup.inn)
        all_startups = (await session.execute(stmt)).all()
        
        # Get startups that already have news to skip them and resume correctly
        existing_news = (await session.execute(
            select(ExternalData.startup_id).where(ExternalData.source == "news")
        )).scalars().all()
        existing_set = set(existing_news)
        
        startups = [s for s in all_startups if s.id not in existing_set]
        
        logger.info(f"Found {len(startups)} startups remaining to process for news (out of {len(all_startups)} total).")
        
        # Process in batches to avoid overwhelming Google
        batch_size = 10
        
        async with httpx.AsyncClient() as client:
            for i in range(0, len(startups), batch_size):
                batch = startups[i:i+batch_size]
                
                for startup_id, name, inn in batch:
                    # Clean name (remove quotes, ООО, ЗАО)
                    clean_name = name.replace('ООО', '').replace('ЗАО', '').replace('АО', '').replace('"', '').strip()
                    
                    # Search query (Name + "стартап" or just Name)
                    query = f'"{clean_name}"'
                    
                    logger.info(f"Fetching news for: {clean_name}")
                    news = await fetch_google_news(client, query)
                    
                    if not news:
                        # Fallback query without quotes if nothing found
                        news = await fetch_google_news(client, clean_name)
                    
                    if news:
                        logger.info(f"Found {len(news)} news articles for {clean_name}")
                        
                        # Store in ExternalData
                        data_json = json.dumps({"articles": news}, ensure_ascii=False)
                        
                        # Check if exists
                        existing = (await session.execute(
                            select(ExternalData).where(
                                ExternalData.startup_id == startup_id,
                                ExternalData.source == "news"
                            )
                        )).scalars().first()
                        
                        if existing:
                            existing.data_json = data_json
                            existing.fetched_at = datetime.utcnow()
                        else:
                            new_record = ExternalData(
                                startup_id=startup_id,
                                source="news",
                                source_authority=0.6,
                                data_json=data_json
                            )
                            session.add(new_record)
                        
                        await session.commit()
                
                # Small delay to prevent rate limiting
                logger.info(f"Processed batch {i//batch_size + 1}/{(len(startups) + batch_size - 1)//batch_size}. Sleeping 2 seconds...")
                await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(process_batch())