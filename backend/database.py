"""
Database connection for PostgreSQL (Railway) with pgvector support.

Env vars (set in Railway Variables or .env):
    DATABASE_URL  -- full postgres:// connection string
                     Railway auto-sets this when you add a Postgres plugin.
    DATABASE_URL_FALLBACK -- optional sqlite:///./local.db for local dev
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

_raw_url = os.environ.get("DATABASE_URL", "")

if _raw_url:
    # Railway gives postgres:// but asyncpg needs postgresql+asyncpg://
    if _raw_url.startswith("postgres://"):
        _raw_url = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif _raw_url.startswith("postgresql://"):
        _raw_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    DATABASE_URL = _raw_url
else:
    # Local fallback: async sqlite via aiosqlite
    DATABASE_URL = os.environ.get(
        "DATABASE_URL_FALLBACK", "sqlite+aiosqlite:///./local_backend.db"
    )

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables (safe to call multiple times)."""
    async with engine.begin() as conn:
        # Enable pgvector extension if PostgreSQL
        if "postgresql" in DATABASE_URL:
            await conn.execute(
                __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
            )
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
