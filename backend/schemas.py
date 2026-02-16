"""Pydantic schemas for FastAPI request / response models."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

class StartupBrief(BaseModel):
    id: str
    name: str
    cluster: str = ""
    status: str = ""
    year_founded: Optional[int] = None
    score_overall: float = 0
    ml_score: Optional[float] = None

    class Config:
        from_attributes = True


class StartupDetail(StartupBrief):
    website: str = ""
    company_description: str = ""
    technologies: str = ""
    industries: str = ""
    inn: str = ""
    ogrn: str = ""
    trl: int = 0
    irl: int = 0
    mrl: int = 0
    crl: int = 0
    patent_count: int = 0
    score_tech_maturity: float = 0
    score_innovation: float = 0
    score_market_potential: float = 0
    score_team_readiness: float = 0
    score_financial_health: float = 0
    ml_tech_maturity: Optional[float] = None
    ml_innovation: Optional[float] = None
    ml_market_potential: Optional[float] = None
    ml_team_readiness: Optional[float] = None
    ml_financial_health: Optional[float] = None
    explanation: Optional[dict] = None  # SHAP values
    external_data: Optional[dict] = None  # Enrichment data summary


class FinancialRecord(BaseModel):
    year: int
    revenue: float = 0
    profit: float = 0


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    model_type: str = "standard"
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict = Field(default_factory=dict)
    user_id: Optional[int] = None


class SearchResult(BaseModel):
    startup: StartupBrief
    rag_similarity: float = 0
    ai_relevance: float = 0
    ml_score: Optional[float] = None


class SearchResponse(BaseModel):
    query_id: int
    results: list[SearchResult]
    total_candidates: int = 0


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

class ScoreRequest(BaseModel):
    startup_id: str


class ScoreResponse(BaseModel):
    startup_id: str
    name: str
    scores: dict  # all proxy + ML scores
    ml_score: Optional[float] = None
    explanation: Optional[dict] = None  # SHAP explanation


# ---------------------------------------------------------------------------
# Score Pipeline (Phase 4 full pipeline)
# ---------------------------------------------------------------------------

class SHAPContribution(BaseModel):
    feature: str
    contribution: float
    value: float


class ScoreExplanation(BaseModel):
    predicted_score: float
    base_value: float
    top_positive: list[SHAPContribution] = []
    top_negative: list[SHAPContribution] = []


class FullScoreResponse(BaseModel):
    startup_id: str
    name: str
    proxy_scores: dict  # 6 proxy scores (1-10)
    ml_scores: Optional[dict] = None  # 6 ML scores (1-10)
    ml_model_version: Optional[str] = None
    explanation: Optional[dict] = None  # SHAP for overall
    all_explanations: Optional[dict] = None  # SHAP for all 6 targets
    financials: list[FinancialRecord] = []
    external_data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

class EnrichRequest(BaseModel):
    startup_id: str


class EnrichResponse(BaseModel):
    startup_id: str
    results: dict


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class SystemStats(BaseModel):
    total_startups: int = 0
    total_users: int = 0
    total_queries: int = 0
    avg_overall_score: float = 0
    ml_model_version: Optional[str] = None
    enrichment_coverage: Optional[dict] = None
