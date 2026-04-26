import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_session
from backend.models import WebUser, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["web_admin"])

# --- Web User Management Schemas ---

class WebUserResponse(BaseModel):
    id: int
    email: str
    role: str
    first_name: str
    last_name: str
    company_name: str
    tg_username: Optional[str] = None
    created_at: str

class UserRoleUpdateRequest(BaseModel):
    user_id: int
    new_role: str  # 'investor', 'startup', 'admin', 'blocked'

class AdminDashboardStats(BaseModel):
    total_users: int
    total_investors: int
    total_startups: int
    total_search_queries: int


@router.get("/users", response_model=List[WebUserResponse])
async def get_all_users(session: AsyncSession = Depends(get_session)):
    """Получить список всех пользователей платформы (для админки)"""
    # В реальном приложении здесь должна быть проверка роли админа
    result = await session.execute(select(WebUser).order_by(WebUser.created_at.desc()))
    users = result.scalars().all()
    
    return [
        WebUserResponse(
            id=u.id,
            email=u.email or "Не указан",
            role=u.role,
            first_name=u.first_name,
            last_name=u.last_name,
            company_name=u.company_name,
            tg_username=u.tg_username,
            created_at=str(u.created_at)
        )
        for u in users
    ]


@router.post("/users/role")
async def update_user_role(req: UserRoleUpdateRequest, session: AsyncSession = Depends(get_session)):
    """Изменить роль пользователя (выдать/отобрать права)"""
    result = await session.execute(select(WebUser).where(WebUser.id == req.user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
        
    valid_roles = ["investor", "startup", "expert", "admin", "blocked"]
    if req.new_role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Недопустимая роль. Доступные: {valid_roles}")
        
    user.role = req.new_role
    await session.commit()
    
    return {"status": "success", "user_id": user.id, "new_role": user.role}


@router.get("/stats", response_model=AdminDashboardStats)
async def get_admin_stats(session: AsyncSession = Depends(get_session)):
    """Статистика для дашборда администратора"""
    total_users = (await session.execute(select(func.count(WebUser.id)))).scalar() or 0
    total_investors = (await session.execute(select(func.count(WebUser.id)).where(WebUser.role == 'investor'))).scalar() or 0
    total_startups = (await session.execute(select(func.count(WebUser.id)).where(WebUser.role == 'startup'))).scalar() or 0
    total_queries = (await session.execute(select(func.count(Query.id)))).scalar() or 0
    
    return AdminDashboardStats(
        total_users=total_users,
        total_investors=total_investors,
        total_startups=total_startups,
        total_search_queries=total_queries
    )
