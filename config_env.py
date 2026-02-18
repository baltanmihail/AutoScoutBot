# Конфигурация из переменных окружения (.env или Railway Variables).
# Используется, если нет config.py (локальный файл с секретами).

import os
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_int_list(key: str, default: list = None) -> list:
    s = _env(key)
    if not s:
        return default or []
    s = s.strip().strip("[]")
    result = []
    for x in s.split(","):
        x = x.strip().strip("[]")
        if not x:
            continue
        try:
            result.append(int(x))
        except ValueError:
            continue
    return result if result else (default or [])


# ============================================================================
# Secrets
# ============================================================================
TELEGRAM_TOKEN = _env("TELEGRAM_TOKEN")
SKOLKOVO_DATABASE_PATH = _env("SKOLKOVO_DATABASE_PATH", "SkolkovoStartups.csv")
SYSTEM_PROMPT_PATH = _env("SYSTEM_PROMPT_PATH", "system_prompt.txt")
USERS_DB_FILE_NAME = _env("USERS_DB_FILE_NAME", "users.db")

# GigaChat -- RAG Embeddings + _internal (re-ranking, smart search)
GIGACHAT_API_TOKEN = _env("GIGACHAT_API_TOKEN")

# ============================================================================
# NeuroAPI (OpenAI-compatible) -- LLM-провайдер для пользовательских запросов
# ============================================================================
LLM_API_KEY = _env("NEUROAPI_KEY", _env("LLM_API_KEY"))
LLM_BASE_URL = _env("NEUROAPI_BASE_URL", _env("LLM_BASE_URL", "https://neuroapi.host/v1"))

LLM_MODELS = {
    "standard": _env("LLM_MODEL_STANDARD", "gemini-3-pro-preview"),
    "premium":  _env("LLM_MODEL_PREMIUM",  "claude-sonnet-4-5-20250929-thinking"),
    "ultra":    _env("LLM_MODEL_ULTRA",    "claude-opus-4-6-thinking"),
    "_internal": "gigachat",
}

LLM_TOKEN_LIMITS = {
    "standard": {
        "filters": 1500,
        "recommendations": 800,
        "temperature_filters": 0.15,
        "temperature_recommendations": 0.5,
    },
    "premium": {
        "filters": 2000,
        "recommendations": 2000,
        "temperature_filters": 0.1,
        "temperature_recommendations": 0.55,
    },
    "ultra": {
        "filters": 2000,
        "recommendations": 3000,
        "temperature_filters": 0.1,
        "temperature_recommendations": 0.6,
    },
    "_internal": {
        "filters": 1500,
        "recommendations": 0,
        "temperature_filters": 0.2,
        "temperature_recommendations": 0.0,
    },
}

# Реальные цены NeuroAPI (руб. за 1M токенов, февраль 2026)
LLM_TOKEN_PRICES = {
    "standard": {"input": 134.30, "output": 805.80},
    "premium":  {"input": 376.04, "output": 1880.20},
    "ultra":    {"input": 335.75, "output": 1678.75},
    "_internal": {"input": 0,     "output": 0},
}

REQUEST_PRICES = {
    "standard": {3: 10, 5: 15, 10: 25},
    "premium":  {3: 25, 5: 40, 10: 70},
    "ultra":    {3: 35, 5: 55, 10: 95},
}

# ============================================================================
# Backward compatibility aliases
# ============================================================================
# Old code references GIGACHAT_MODELS / GIGACHAT_TOKEN_LIMITS / GIGACHAT_TOKEN_PRICES.
# Map them to the new names so nothing breaks.
GIGACHAT_MODELS = LLM_MODELS
GIGACHAT_TOKEN_LIMITS = LLM_TOKEN_LIMITS
GIGACHAT_TOKEN_PRICES = LLM_TOKEN_PRICES

# ============================================================================
# Admin
# ============================================================================
ADMIN_IDS = _env_int_list("ADMIN_IDS", [5079636941, 1856746424])

# ============================================================================
# RAG (still uses GigaChat Embeddings -- free / cheap)
# ============================================================================
RAG_ENABLED = _env("RAG_ENABLED", "true").lower() in ("1", "true", "yes")
RAG_INDEX_FILE = _env("RAG_INDEX_FILE", "rag_index_gigachat.json")
RAG_TOP_K = int(_env("RAG_TOP_K", "200"))

# ============================================================================
# Continuous learning
# ============================================================================
CONTINUOUS_LEARNING = {
    "enabled": _env("CONTINUOUS_LEARNING_ENABLED", "true").lower() in ("1", "true", "yes"),
    "light_learning": True,
    "queries_threshold": int(_env("CONTINUOUS_LEARNING_QUERIES_THRESHOLD", "10")),
    "hours_interval": int(_env("CONTINUOUS_LEARNING_HOURS_INTERVAL", "24")),
}

SELF_LEARNING = {
    "min_samples": 3,
    "min_ai_relevance": 80,
    "max_patterns": 50,
    "max_few_shot_examples": 10,
}

FINE_TUNING = {
    "min_examples": 100,
    "output_file": "finetuning_dataset.jsonl",
    "include_rag_similarity": True,
}

# Backend API URL (for bot -> FastAPI communication)
BACKEND_URL = _env("BACKEND_URL", "http://localhost:8000")

# Data enrichment
ENABLE_ENRICHMENT = _env("ENABLE_ENRICHMENT", "true").lower() in ("1", "true", "yes")
ENRICHMENT_INTERVAL_HOURS = int(_env("ENRICHMENT_INTERVAL_HOURS", "6"))

# For backward compat with domain/admin.py
AI_MODELS = {k: {"name": v} for k, v in LLM_MODELS.items()}
