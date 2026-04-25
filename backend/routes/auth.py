import logging
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

class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "investor"  # investor or startup
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    company_name: Optional[str] = ""

class AuthResponse(BaseModel):
    token: str
    role: str
    email: str


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)):
    # 1. Проверяем, есть ли уже такой пользователь
    result = await session.execute(select(WebUser).where(WebUser.email == req.email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже зарегистрирован."
        )

    # В MVP-версии пароль храним как есть (в продакшене обязательно хешируем, например через bcrypt!)
    new_user = WebUser(
        email=req.email,
        hashed_password=req.password,  # TODO: add bcrypt hash
        role=req.role,
        first_name=req.first_name,
        last_name=req.last_name,
        company_name=req.company_name
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    # Генерируем "токен" (заглушка для фронтенда)
    fake_token = f"fake_jwt_token_for_{new_user.id}"

    return AuthResponse(
        token=fake_token,
        role=new_user.role,
        email=new_user.email
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

    fake_token = f"fake_jwt_token_for_{user.id}"

    return AuthResponse(
        token=fake_token,
        role=user.role,
        email=user.email
    )
