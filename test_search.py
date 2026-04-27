import asyncio
import os
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:password@localhost:5432/autoscout"

from sqlalchemy import select, or_
import re
from backend.database import engine, get_session
from backend.models import Startup, StartupScore

async def test():
    query_lower = "b2b saas для автоматизации кадров или hr, желательно с интеграцией в 1с. ищем замену ушедшим западным вендорам, выручка от 10 млн, стадия не ниже mvp"
    words = re.findall(r'\b\w{3,}\b', query_lower)
    words = words[:10]
    
    full_pattern = f"%{query_lower}%"
    conditions = [
        Startup.name.ilike(full_pattern),
        Startup.inn.ilike(full_pattern),
        Startup.company_description.ilike(full_pattern)
    ]
    
    for word in words:
        like_pattern = f"%{word}%"
        conditions.append(
            Startup.name.ilike(like_pattern) |
            Startup.company_description.ilike(like_pattern) |
            Startup.technologies.ilike(like_pattern) |
            Startup.industries.ilike(like_pattern) |
            Startup.product_names.ilike(like_pattern)
        )
        
    stmt = (
        select(Startup, StartupScore)
        .outerjoin(StartupScore, Startup.id == StartupScore.startup_id)
        .where(Startup.status != "")
    )
    if conditions:
        stmt = stmt.where(or_(*conditions))
        
    print(stmt.compile(compile_kwargs={"literal_binds": True}))
    
    async with engine.connect() as conn:
        res = await conn.execute(select(Startup).limit(1))
        print("Test select 1:", res.first())
        
        res2 = await conn.execute(stmt)
        print("Count:", len(res2.all()))

asyncio.run(test())
