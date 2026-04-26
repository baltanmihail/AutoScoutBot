import asyncio
import os
import sys

# Добавляем корневую директорию проекта в sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.database import get_session
from backend.models import WebUser
from sqlalchemy.future import select

async def make_admin(email_or_tg_username: str):
    async for session in get_session():
        # Ищем по email или tg_username
        result = await session.execute(
            select(WebUser).where(
                (WebUser.email == email_or_tg_username) | 
                (WebUser.tg_username == email_or_tg_username)
            )
        )
        user = result.scalars().first()
        
        if user:
            user.role = 'admin'
            await session.commit()
            print(f"✅ Пользователь {email_or_tg_username} успешно назначен администратором!")
        else:
            print(f"❌ Пользователь {email_or_tg_username} не найден в базе данных.")
        return

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python make_admin.py <email_или_tg_username>")
        sys.exit(1)
        
    asyncio.run(make_admin(sys.argv[1]))