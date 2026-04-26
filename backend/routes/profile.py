import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.database import get_session
from backend.models import WebUser
from backend.routes.auth import TelegramAuthRequest
import os
import hashlib
import hmac
import time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile"])

class ProfileResponse(BaseModel):
    id: int
    email: str
    role: str
    first_name: str
    last_name: str
    middle_name: Optional[str] = None
    company_name: str
    phone: Optional[str] = None
    tg_username: Optional[str] = None
    tg_photo_url: Optional[str] = None

class ProfileUpdateRequest(BaseModel):
    first_name: str
    last_name: str
    middle_name: Optional[str] = ""
    company_name: str
    phone: str

async def get_current_user_from_token(token: str, session: AsyncSession) -> WebUser:
    if not token.startswith("Bearer fake_jwt_token_for_"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")
    
    try:
        user_id_str = token.replace("Bearer fake_jwt_token_for_", "")
        user_id = int(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user id in token")
        
    result = await session.execute(select(WebUser).where(WebUser.id == user_id))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        
    return user


from fastapi import Header

@router.get("", response_model=ProfileResponse)
async def get_profile(authorization: str = Header(...), session: AsyncSession = Depends(get_session)):
    """Получение данных профиля текущего пользователя"""
    user = await get_current_user_from_token(authorization, session)
    
    return ProfileResponse(
        id=user.id,
        email=user.email or f"tg_{user.tg_id}@telegram.local" if user.tg_id else "Не указан",
        role=user.role,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        middle_name=user.middle_name or "",
        company_name=user.company_name or "",
        phone=user.phone,
        tg_username=user.tg_username,
        tg_photo_url=user.tg_photo_url
    )

@router.post("/link_telegram", response_model=ProfileResponse)
async def link_telegram(
    req: TelegramAuthRequest,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Привязка Telegram аккаунта к существующему профилю"""
    user = await get_current_user_from_token(authorization, session)
    
    bot_token = os.getenv("TELEGRAM_TOKEN", "")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Telegram token not configured on server")

    # Проверка хэша
    data_check_arr = []
    data_dict = req.dict(exclude={"hash", "role"})
    for key, value in data_dict.items():
        if value is not None:
            data_check_arr.append(f"{key}={value}")
    
    data_check_arr.sort()
    data_check_string = "\n".join(data_check_arr)
    
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if expected_hash != req.hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram hash")
        
    if time.time() - req.auth_date > 86400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram auth data expired")

    # Проверка, не привязан ли этот TG ID к другому аккаунту
    result = await session.execute(select(WebUser).where(WebUser.tg_id == req.id))
    existing_tg_user = result.scalars().first()
    
    if existing_tg_user and existing_tg_user.id != user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Этот Telegram аккаунт уже привязан к другому профилю")

    user.tg_id = req.id
    user.tg_username = req.username
    user.tg_first_name = req.first_name
    user.tg_photo_url = req.photo_url
    
    await session.commit()
    await session.refresh(user)
    
    return ProfileResponse(
        id=user.id,
        email=user.email or f"tg_{user.tg_id}@telegram.local" if user.tg_id else "Не указан",
        role=user.role,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        middle_name=user.middle_name or "",
        company_name=user.company_name or "",
        phone=user.phone,
        tg_username=user.tg_username,
        tg_photo_url=user.tg_photo_url
    )
@router.put("", response_model=ProfileResponse)
async def update_profile(
    req: ProfileUpdateRequest,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Обновление данных профиля"""
    user = await get_current_user_from_token(authorization, session)
    
    user.first_name = req.first_name
    user.last_name = req.last_name
    user.middle_name = req.middle_name
    user.company_name = req.company_name
    user.phone = req.phone
    
    await session.commit()
    await session.refresh(user)
    
    return ProfileResponse(
        id=user.id,
        email=user.email or f"tg_{user.tg_id}@telegram.local" if user.tg_id else "Не указан",
        role=user.role,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        middle_name=user.middle_name or "",
        company_name=user.company_name or "",
        phone=user.phone,
        tg_username=user.tg_username,
        tg_photo_url=user.tg_photo_url
    )
