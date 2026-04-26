import logging
import time
import os
import hashlib
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.database import get_session
from backend.models import WebUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

import random

class VerifyCodeRequest(BaseModel):
    email: str
    code: str

class SendCodeRequest(BaseModel):
    email: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "investor"  # investor or startup
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    middle_name: Optional[str] = ""
    company_name: Optional[str] = ""
    phone: Optional[str] = ""

class TelegramAuthRequest(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str
    role: str = "investor"

class AuthResponse(BaseModel):
    token: str
    role: str
    email: str
    tg_username: Optional[str] = None
    tg_photo_url: Optional[str] = None


class VerifyResponse(BaseModel):
    message: str
    email: str

@router.post("/register", response_model=VerifyResponse)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(WebUser).where(WebUser.email == req.email))
    existing_user = result.scalars().first()
    if existing_user:
        if existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пользователь с таким email уже зарегистрирован."
            )
        else:
            # Re-generate code for unverified user
            verification_code = str(random.randint(100000, 999999))
            existing_user.verification_code = verification_code
            existing_user.hashed_password = req.password
            existing_user.role = req.role
            existing_user.first_name = req.first_name
            existing_user.last_name = req.last_name
            existing_user.middle_name = req.middle_name
            existing_user.company_name = req.company_name
            existing_user.phone = req.phone
            
            await session.commit()
            logger.info(f"VERIFICATION CODE for {req.email}: {verification_code}")
            return VerifyResponse(message="Код отправлен на почту", email=req.email)

    verification_code = str(random.randint(100000, 999999))
    
    # TODO: bcrypt
    new_user = WebUser(
        email=req.email,
        hashed_password=req.password,
        role=req.role,
        first_name=req.first_name,
        last_name=req.last_name,
        middle_name=req.middle_name,
        company_name=req.company_name,
        phone=req.phone,
        is_verified=False,
        verification_code=verification_code
    )
    session.add(new_user)
    await session.commit()
    
    # Mocking email sending
    logger.info(f"VERIFICATION CODE for {req.email}: {verification_code}")

    return VerifyResponse(message="Код отправлен на почту", email=req.email)


@router.post("/verify", response_model=AuthResponse)
async def verify_code(req: VerifyCodeRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(WebUser).where(WebUser.email == req.email))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
        
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Пользователь уже верифицирован")
        
    if user.verification_code != req.code:
        raise HTTPException(status_code=400, detail="Неверный код подтверждения")
        
    user.is_verified = True
    user.verification_code = None
    
    await session.commit()
    await session.refresh(user)
    
    fake_token = f"fake_jwt_token_for_{user.id}"

    return AuthResponse(
        token=fake_token,
        role=user.role,
        email=user.email or ""
    )

@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(WebUser).where(WebUser.email == req.email, WebUser.hashed_password == req.password)
    )
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль."
        )
        
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Электронная почта не подтверждена. Пожалуйста, пройдите регистрацию заново, чтобы получить код."
        )

    fake_token = f"fake_jwt_token_for_{user.id}"

    return AuthResponse(
        token=fake_token,
        role=user.role,
        email=user.email or ""
    )


@router.post("/telegram", response_model=AuthResponse)
async def telegram_auth(req: TelegramAuthRequest, session: AsyncSession = Depends(get_session)):
    """Аутентификация через Telegram Widget"""
    
    bot_token = os.getenv("TELEGRAM_TOKEN", "")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Telegram token not configured on server")

    # 1. Проверяем подлинность хэша от Telegram
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
        
    # 2. Проверяем устаревание (не старше 24 часов)
    if time.time() - req.auth_date > 86400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telegram auth data expired")

    # 3. Ищем пользователя по tg_id или создаем нового
    result = await session.execute(select(WebUser).where(WebUser.tg_id == req.id))
    user = result.scalars().first()
    
    if not user:
        user = WebUser(
            tg_id=req.id,
            tg_username=req.username,
            tg_first_name=req.first_name,
            tg_photo_url=req.photo_url,
            first_name=req.first_name,
            last_name=req.last_name or "",
            role=req.role
        )
        session.add(user)
    else:
        # Обновляем профиль если изменился
        user.tg_username = req.username
        user.tg_first_name = req.first_name
        user.tg_photo_url = req.photo_url

    await session.commit()
    await session.refresh(user)
    
    fake_token = f"fake_jwt_token_for_{user.id}"
    
    return AuthResponse(
        token=fake_token,
        role=user.role,
        email=user.email or f"tg_{req.id}@telegram.local",
        tg_username=user.tg_username,
        tg_photo_url=user.tg_photo_url
    )
