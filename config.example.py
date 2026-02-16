# Скопируйте в config.py и заполните значения.
# Либо задайте переменные окружения (см. README и docs) — тогда config_env подхватит их.

TELEGRAM_TOKEN = ""  # Токен бота от @BotFather
SKOLKOVO_DATABASE_PATH = "SkolkovoStartups.csv"
GIGACHAT_API_TOKEN = ""  # Токен GigaChat API
SYSTEM_PROMPT_PATH = "system_prompt.txt"
USERS_DB_FILE_NAME = "users.db"

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
    "standard": {"filters": 1500, "recommendations": 0, "temperature_filters": 0.2, "temperature_recommendations": 0.0},
    "pro": {"filters": 0, "recommendations": 500, "temperature_filters": 0.0, "temperature_recommendations": 0.5},
    "max": {"filters": 300, "recommendations": 250, "temperature_filters": 0.1, "temperature_recommendations": 0.6},
}

ADMIN_IDS = []  # Список Telegram user_id админов, например [123456789]

RAG_ENABLED = True
RAG_INDEX_FILE = "rag_index_gigachat.json"
RAG_TOP_K = 200

CONTINUOUS_LEARNING = {
    "enabled": True,
    "light_learning": True,
    "queries_threshold": 10,
    "hours_interval": 24,
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

# Для domain/admin.py
AI_MODELS = {k: {"name": v} for k, v in GIGACHAT_MODELS.items()}
