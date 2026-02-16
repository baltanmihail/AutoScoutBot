# Конфигурация из переменных окружения (.env или Railway Variables).
# Используется, если нет config_local.py (см. config.example.py и README).

import os
from dotenv import load_dotenv

load_dotenv()

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()

def _env_int_list(key: str, default: list = None) -> list:
    s = _env(key)
    if not s:
        return default or []
    # Поддержка форматов: "1,2,3" или "[1, 2, 3]" (как в Railway)
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

# Секреты и пути (обязательно задать в .env или Railway)
TELEGRAM_TOKEN = _env("TELEGRAM_TOKEN")
SKOLKOVO_DATABASE_PATH = _env("SKOLKOVO_DATABASE_PATH", "SkolkovoStartups.csv")
GIGACHAT_API_TOKEN = _env("GIGACHAT_API_TOKEN")
SYSTEM_PROMPT_PATH = _env("SYSTEM_PROMPT_PATH", "system_prompt.txt")
USERS_DB_FILE_NAME = _env("USERS_DB_FILE_NAME", "users.db")

# Админы: в env как "5079636941,1856746424"
ADMIN_IDS = _env_int_list("ADMIN_IDS", [5079636941, 1856746424])

# Модели GigaChat
GIGACHAT_MODELS = {
    "standard": "GigaChat",
    "pro": "GigaChat-Pro",
    "max": "GigaChat-Max"
}

REQUEST_PRICES = {
    "standard": {3: 25, 5: 35, 10: 65},
    "pro": {3: 35, 5: 45, 10: 75},
    "max": {3: 45, 5: 55, 10: 85}
}

GIGACHAT_TOKEN_PRICES = {
    "standard": {"input": 0, "output": 0},
    "pro": {"input": 200, "output": 400},
    "max": {"input": 600, "output": 1200}
}

GIGACHAT_TOKEN_LIMITS = {
    "standard": {
        "filters": 1500,
        "recommendations": 0,
        "temperature_filters": 0.2,
        "temperature_recommendations": 0.0,
    },
    "pro": {
        "filters": 0,
        "recommendations": 500,
        "temperature_filters": 0.0,
        "temperature_recommendations": 0.5,
    },
    "max": {
        "filters": 300,
        "recommendations": 250,
        "temperature_filters": 0.1,
        "temperature_recommendations": 0.6,
    }
}

# RAG
RAG_ENABLED = _env("RAG_ENABLED", "true").lower() in ("1", "true", "yes")
RAG_INDEX_FILE = _env("RAG_INDEX_FILE", "rag_index_gigachat.json")
RAG_TOP_K = int(_env("RAG_TOP_K", "200"))

# Самообучение (числа через env опционально)
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

# Для совместимости с domain/admin.py: AI_MODELS[model]['name']
AI_MODELS = {k: {"name": v} for k, v in GIGACHAT_MODELS.items()}
