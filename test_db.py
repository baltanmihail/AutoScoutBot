import asyncio
import os

from sqlalchemy import select, func
from backend.database import engine, get_session
from backend.models import Startup, StartupScore

async def test():
    async with engine.connect() as conn:
        res = await conn.execute(select(func.count(Startup.id)).where(Startup.status != ""))
        count_not_empty = res.scalar()
        
        res = await conn.execute(select(func.count(Startup.id)).where(Startup.status.is_(None)))
        count_null = res.scalar()

        res = await conn.execute(select(func.count(Startup.id)).where(Startup.status == ""))
        count_empty = res.scalar()

        res = await conn.execute(select(func.count(Startup.id)))
        count_total = res.scalar()
        
        print(f"Total startups: {count_total}")
        print(f"Status != '': {count_not_empty}")
        print(f"Status IS NULL: {count_null}")
        print(f"Status == '': {count_empty}")

asyncio.run(test())
