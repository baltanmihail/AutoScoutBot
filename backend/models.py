"""
SQLAlchemy ORM models -- PostgreSQL schema for AutoScoutBot v2.

Tables
------
startups            -- core startup data (migrated from CSV)
startup_scores      -- ML model + expert scores
startup_financials  -- normalised yearly financials
startup_embeddings  -- pgvector embeddings (1024-dim default)
external_data       -- parsed data from EGRUL / Checko / news
users               -- Telegram users
purchases           -- payment history
queries             -- search queries
query_results       -- per-query results with relevance scores
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base

# ---------------------------------------------------------------------------
# Startups
# ---------------------------------------------------------------------------

class Startup(Base):
    __tablename__ = "startups"

    id = Column(String(64), primary_key=True)  # md5 of name
    name = Column(String(512), nullable=False, index=True)
    website = Column(String(512), default="")
    company_description = Column(Text, default="")
    project_description = Column(Text, default="")
    product_description = Column(Text, default="")
    full_legal_name = Column(String(1024), default="")
    inn = Column(String(20), default="", index=True)
    ogrn = Column(String(20), default="", index=True)
    year_founded = Column(Integer, nullable=True)
    status = Column(String(50), default="", index=True)
    cluster = Column(String(128), default="", index=True)
    category = Column(Text, default="")
    region = Column(Text, default="")
    technologies = Column(Text, default="")
    industries = Column(Text, default="")
    product_names = Column(Text, default="")
    project_names = Column(Text, default="")
    patents = Column(Text, default="")

    # Readiness levels (parsed integers 0-9)
    trl = Column(Integer, default=0)
    irl = Column(Integer, default=0)
    mrl = Column(Integer, default=0)
    crl = Column(Integer, default=0)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    scores = relationship("StartupScore", back_populates="startup", uselist=False)
    financials = relationship("StartupFinancial", back_populates="startup")
    external = relationship("ExternalData", back_populates="startup")

    __table_args__ = (
        Index("ix_startups_cluster_status", "cluster", "status"),
    )


class StartupScore(Base):
    __tablename__ = "startup_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    startup_id = Column(String(64), ForeignKey("startups.id"), unique=True, nullable=False)

    # Proxy scores (Phase 0 labeler)
    score_tech_maturity = Column(Float, default=0)
    score_innovation = Column(Float, default=0)
    score_market_potential = Column(Float, default=0)
    score_team_readiness = Column(Float, default=0)
    score_financial_health = Column(Float, default=0)
    score_overall = Column(Float, default=0, index=True)

    # ML model predictions (Phase 2, initially NULL)
    ml_score = Column(Float, nullable=True)
    ml_model_version = Column(String(64), nullable=True)

    # Expert scores (if available)
    expert_score = Column(Float, nullable=True)
    expert_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    startup = relationship("Startup", back_populates="scores")


class StartupFinancial(Base):
    __tablename__ = "startup_financials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    startup_id = Column(String(64), ForeignKey("startups.id"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    revenue = Column(Float, default=0)
    profit = Column(Float, default=0)

    startup = relationship("Startup", back_populates="financials")

    __table_args__ = (
        Index("ix_fin_startup_year", "startup_id", "year", unique=True),
    )


class ExternalData(Base):
    __tablename__ = "external_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    startup_id = Column(String(64), ForeignKey("startups.id"), nullable=False, index=True)
    source = Column(String(64), nullable=False)  # egrul, checko, news, fips
    source_authority = Column(Float, default=0.5)  # 0-1, higher = more trusted
    data_json = Column(Text, default="{}")
    fetched_at = Column(DateTime, default=func.now())

    startup = relationship("Startup", back_populates="external")


# ---------------------------------------------------------------------------
# Embeddings (pgvector -- Phase 4)
# ---------------------------------------------------------------------------

try:
    from pgvector.sqlalchemy import Vector

    class StartupEmbedding(Base):
        __tablename__ = "startup_embeddings"

        id = Column(Integer, primary_key=True, autoincrement=True)
        startup_id = Column(String(64), ForeignKey("startups.id"), unique=True, nullable=False, index=True)
        embedding = Column(Vector(384))  # dimension matches MiniLM-L12-v2
        model_version = Column(String(64), default="paraphrase-multilingual-MiniLM-L12-v2")
        created_at = Column(DateTime, default=func.now())

except ImportError:
    # pgvector not installed -- provide a placeholder for non-PostgreSQL envs
    class StartupEmbedding(Base):  # type: ignore[no-redef]
        __tablename__ = "startup_embeddings"

        id = Column(Integer, primary_key=True, autoincrement=True)
        startup_id = Column(String(64), ForeignKey("startups.id"), unique=True, nullable=False, index=True)
        embedding = Column(Text, default="")  # serialised JSON fallback
        model_version = Column(String(64), default="")
        created_at = Column(DateTime, default=func.now())


# ---------------------------------------------------------------------------
# Users & Payments (mirroring existing SQLite schema)
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    requests_standard = Column(Integer, default=3)
    requests_pro = Column(Integer, default=0)
    requests_max = Column(Integer, default=0)
    is_banned = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    purchases = relationship("Purchase", back_populates="user")


class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    model_type = Column(String(20), nullable=False)
    requests_amount = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    stars_spent = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="purchases")


# ---------------------------------------------------------------------------
# Search queries & results
# ---------------------------------------------------------------------------

class Query(Base):
    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    query_text = Column(Text, nullable=False)
    expanded_query = Column(Text, default="")
    model_type = Column(String(20), default="standard")
    filters_used = Column(Text, default="{}")
    created_at = Column(DateTime, default=func.now())

    results = relationship("QueryResult", back_populates="query")


class QueryResult(Base):
    __tablename__ = "query_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(Integer, ForeignKey("queries.id"), nullable=False, index=True)
    startup_id = Column(String(64), nullable=False)
    startup_name = Column(String(512), default="")
    rag_similarity = Column(Float, default=0)
    ai_relevance = Column(Float, default=0)
    ml_score = Column(Float, nullable=True)
    position = Column(Integer, default=0)
    cluster = Column(String(128), default="")
    technologies = Column(Text, default="")

    query = relationship("Query", back_populates="results")
