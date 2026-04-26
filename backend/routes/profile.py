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
    requests_standard: int = 3
    requests_pro: int = 0
    requests_max: int = 0
    is_verified: bool = False
    is_phone_verified: bool = False

class ProfileUpdateRequest(BaseModel):
    email: str
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


from fastapi import Header, Query

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
        tg_photo_url=user.tg_photo_url,
        requests_standard=user.requests_standard,
        requests_pro=user.requests_pro,
        requests_max=user.requests_max,
        is_verified=user.is_verified,
        is_phone_verified=(user.phone_verification_code == "OK")
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
        tg_photo_url=user.tg_photo_url,
        requests_standard=user.requests_standard,
        requests_pro=user.requests_pro,
        requests_max=user.requests_max,
        is_verified=user.is_verified,
        is_phone_verified=(user.phone_verification_code == "OK")
    )
@router.put("", response_model=ProfileResponse)
async def update_profile(
    req: ProfileUpdateRequest,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Обновление данных профиля"""
    user = await get_current_user_from_token(authorization, session)
    
    if req.email and req.email != user.email:
        result = await session.execute(select(WebUser).where(WebUser.email == req.email))
        existing_email_user = result.scalars().first()
        if existing_email_user and existing_email_user.id != user.id:
            raise HTTPException(status_code=400, detail="Этот email уже занят другим пользователем")
        user.email = req.email
        user.is_verified = False
        
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
        tg_photo_url=user.tg_photo_url,
        requests_standard=user.requests_standard,
        requests_pro=user.requests_pro,
        requests_max=user.requests_max,
        is_verified=user.is_verified,
        is_phone_verified=(user.phone_verification_code == "OK")
    )

class ProfileVerifyRequest(BaseModel):
    type: str
    code: str

@router.post("/request_verification")
async def request_verification(
    type: str = Query("email", description="Тип подтверждения: email или phone"),
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Запрос кода для подтверждения профиля"""
    user = await get_current_user_from_token(authorization, session)
    
    import random
    from backend.routes.auth import send_email_code, send_sms_code
    
    if type == "email":
        if user.is_verified:
            return {"message": "Email уже подтвержден"}
        verification_code = str(random.randint(100000, 999999))
        user.verification_code = verification_code
        await session.commit()
        
        res = await send_email_code(user.email, verification_code)
        if res is not True:
            raise HTTPException(status_code=500, detail=f"Ошибка SMTP: {res}")
            
        return {"message": "Код отправлен на Email"}
        
    elif type == "phone":
        if not user.phone:
            raise HTTPException(status_code=400, detail="Номер телефона не указан")
        if user.phone_verification_code == "OK":
            return {"message": "Телефон уже подтвержден"}
        phone_verification_code = str(random.randint(100000, 999999))
        user.phone_verification_code = phone_verification_code
        await session.commit()
        
        res = await send_sms_code(user.phone, phone_verification_code)
        if res is not True:
            raise HTTPException(status_code=500, detail=f"Ошибка SMS: {res}")
            
        return {"message": "Код отправлен по СМС"}
        
    raise HTTPException(status_code=400, detail="Неверный тип")

@router.post("/verify")
async def verify_profile(
    req: ProfileVerifyRequest,
    authorization: str = Header(...),
    session: AsyncSession = Depends(get_session)
):
    """Проверка введенного кода"""
    user = await get_current_user_from_token(authorization, session)
    
    if req.type == "email":
        if user.is_verified:
            raise HTTPException(status_code=400, detail="Email уже подтвержден")
        if not user.verification_code or user.verification_code != req.code:
            raise HTTPException(status_code=400, detail="Неверный email код")
        user.is_verified = True
        user.verification_code = None
        
    elif req.type == "phone":
        if user.phone_verification_code == "OK":
            raise HTTPException(status_code=400, detail="Телефон уже подтвержден")
        if not user.phone_verification_code or user.phone_verification_code != req.code:
            raise HTTPException(status_code=400, detail="Неверный СМС код")
        user.phone_verification_code = "OK"
        
    else:
        raise HTTPException(status_code=400, detail="Неверный тип")
        
    await session.commit()
    return {"message": "Успешно подтверждено"}
