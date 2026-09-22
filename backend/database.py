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


async def ensure_vector_column(dim: int) -> bool:
    """
    Convert startup_embeddings.embedding to vector(dim) if the table was created while the
    pgvector package was missing (models.py then declares a text placeholder column).
    Returns True if the column was converted.
    """
    if "postgresql" not in DATABASE_URL:
        return False
    from sqlalchemy import text

    async with engine.begin() as conn:
        data_type = (await conn.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'startup_embeddings' AND column_name = 'embedding'"
        ))).scalar()
        if data_type != "text":
            return False
        # Placeholder rows hold no vectors; drop them so these startups are embedded again
        await conn.execute(text("DELETE FROM startup_embeddings WHERE embedding IS NULL OR embedding = ''"))
        await conn.execute(text(
            f"ALTER TABLE startup_embeddings ALTER COLUMN embedding TYPE vector({int(dim)}) "
            f"USING embedding::vector({int(dim)})"
        ))
        return True


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
