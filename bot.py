import asyncio
import sys

# Конфиг: локальный config.py или переменные окружения (config_env для Railway/.env)
try:
    import config
except ImportError:
    import config_env as config
    sys.modules["config"] = config

from aiogram.client.default import DefaultBotProperties
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage

# ============ Конфигурация ============

from config import TELEGRAM_TOKEN
from data.sqlite_user_repository_impl import SQLiteUserRepositoryImpl
from domain.user_repository import UserRepository
from fallback import Fallback
from gigachat_client import GigaChatClient
from payments import get_payments_router

# Логирование
from logger import logger
from services.payments_service import PaymentsService

# Импорты из utils
from utils.startup_utils import load_skolkovo_database
from utils.filters import parse_criteria_text, create_criteria_keyboard, get_filters
from utils.search_utils import get_unique_startups as get_unique_startups_func

# Импорты обработчиков
from handlers import (
    register_start_handlers,
    register_search_handlers,
    start_search_func,
    register_filters_handlers,
    register_interactive_handlers,
    register_admin_handlers,
)

# ============ Константы и глобальные переменные ============

# Глобальные
shown_startups = set()
available_filters = {}

# Загружаем базу данных Сколково синхронно до регистрации обработчиков
print("🤖 Бот запускается...")
print("📊 Загрузка базы данных Сколково...")
SKOLKOVO_DB, available_filters = load_skolkovo_database()
if SKOLKOVO_DB:
    logger.info(f"Загружено {len(SKOLKOVO_DB)} записей из базы Сколково")
    print(f"✅ База Сколково загружена: {len(SKOLKOVO_DB)} записей")
else:
    print("❌ Не удалось загрузить базу Сколково")
    SKOLKOVO_DB = []

# ML Scoring: pre-warm LightGBM models (trained on Skolkovo expert data)
try:
    from scoring.ml_scoring import _get_predictor
    predictor = _get_predictor()
    if predictor and predictor.is_ready:
        print(f"🧠 ML модель загружена (LightGBM, R²>0.96, version={predictor.version})")
        print(f"   Анализ стартапов теперь использует ML вместо эвристик")
    else:
        print("⚠️ ML модель не найдена, используются эвристики")
except Exception as e:
    print(f"⚠️ ML scoring недоступен: {e}")

gigachat_client = GigaChatClient()
user_repository: UserRepository = SQLiteUserRepositoryImpl()

# RAG Service (импортируем после определения основных переменных)
try:
    from config import RAG_ENABLED, RAG_INDEX_FILE, RAG_TOP_K
    from services.rag_service import RAGService
    from services.reranker import ReRanker
    from services.query_history import QueryHistory
    from services.few_shot_examples import get_few_shot_prompt, detect_query_category
    from ai_learning import get_continuous_learner, IncrementalLearner
    from config import CONTINUOUS_LEARNING
    
    rag_service = RAGService() if RAG_ENABLED else None
    query_history = QueryHistory()
    
    # Инкрементальное обучение (после каждого запроса)
    incremental_learner = IncrementalLearner()
    
    # Запуск continuous learning (глубокое обучение периодически)
    continuous_learner = get_continuous_learner()
    if CONTINUOUS_LEARNING.get('enabled', True):
        continuous_learner.start()
    
    logger.info("✅ RAG Service и модули улучшения импортированы")
    
    if CONTINUOUS_LEARNING.get('light_learning', True):
        logger.info("📚 Инкрементальное обучение: ВКЛ (после каждого запроса)")
    
    queries_threshold = CONTINUOUS_LEARNING.get('queries_threshold', 10)
    logger.info(f"🧠 Continuous Learning запущен (глубокое обучение каждые {queries_threshold} запросов)")
except Exception as e:
    logger.warning(f"⚠️ RAG Service недоступен: {e}")
    RAG_ENABLED = False
    rag_service = None
    query_history = None
    continuous_learner = None

# ============ Бизнес-логика поиска ============

def get_unique_startups(count: int, filters: dict, user_request: str = "", user_id: int = None):
    """Обертка для get_unique_startups из utils/search_utils.py"""
    global shown_startups, SKOLKOVO_DB, rag_service, query_history, continuous_learner, incremental_learner, RAG_ENABLED, RAG_TOP_K
    
    # Создаем копию shown_startups для передачи в функцию
    # Функция обновит его, и мы синхронизируем с глобальной переменной
    result = get_unique_startups_func(
        count=count,
        filters=filters,
        user_request=user_request,
        user_id=user_id,
        SKOLKOVO_DB=SKOLKOVO_DB,
        shown_startups=shown_startups,
        rag_service=rag_service,
        query_history=query_history,
        continuous_learner=continuous_learner,
        incremental_learner=incremental_learner,
        RAG_ENABLED=RAG_ENABLED,
        RAG_TOP_K=RAG_TOP_K
    )
    # Синхронизируем shown_startups (он обновляется внутри функции)
    return result

# ============ Службы =============

payments_service = PaymentsService(user_repository)

# ============ Роутеры ============

payments_router = get_payments_router(payments_service)


bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(payments_router)

# Регистрация обработчиков
start_router = Router()
search_router = Router()
filters_router = Router()
interactive_router = Router()

# Регистрируем обработчики
register_start_handlers(start_router, user_repository)
register_search_handlers(
    search_router, bot, user_repository, gigachat_client,
    get_unique_startups, query_history, SKOLKOVO_DB
)
register_filters_handlers(
    filters_router, bot, user_repository, available_filters,
    lambda event, state, filters: start_search_func(
        event, state, filters, bot, user_repository,
        gigachat_client, get_unique_startups, query_history, SKOLKOVO_DB
    ),
    parse_criteria_text,
    create_criteria_keyboard,
    get_filters
)
register_interactive_handlers(
    interactive_router, bot, user_repository, gigachat_client,
    lambda event, state, filters: start_search_func(
        event, state, filters, bot, user_repository,
        gigachat_client, get_unique_startups, query_history, SKOLKOVO_DB
    )
)

# Регистрация админ-обработчиков (должен быть зарегистрирован ДО Fallback)
admin_router = Router()
register_admin_handlers(
    admin_router, user_repository, rag_service, continuous_learner,
    RAG_ENABLED, RAG_INDEX_FILE, SKOLKOVO_DB
)

dp.include_router(start_router)
dp.include_router(search_router)
dp.include_router(filters_router)
dp.include_router(interactive_router)
dp.include_router(admin_router)
dp.include_router(Fallback.router)  # Fallback должен быть последним

# ============ Точка входа ============

async def on_startup():
    global SKOLKOVO_DB, available_filters, rag_service
    # База данных уже загружена синхронно выше
    
    # Инициализация RAG
    if SKOLKOVO_DB and RAG_ENABLED and rag_service:
        print("🔄 Инициализация RAG-системы...")
        
        # Пытаемся загрузить существующий индекс
        index_loaded = rag_service.load_index(RAG_INDEX_FILE)
        vectors_count = len(rag_service.startup_vectors)
        
        # Если индекс загружен, но пустой - пересоздаем
        if index_loaded and vectors_count == 0:
            print("⚠️ Загружен пустой индекс (старая версия с ошибками)")
            print("🔄 Пересоздание индекса с TF-IDF...")
            index_loaded = False
        
        if index_loaded and vectors_count > 0:
            print(f"✅ RAG индекс загружен: {vectors_count} стартапов")
    else:
            print("🔄 Создание RAG индекса... (это может занять 5-10 минут)")
            print("💡 Индекс создается один раз и сохраняется для быстрой загрузки")
            
            def progress(current, total):
                if current % 500 == 0:
                    print(f"   Проиндексировано: {current}/{total}")
            
            indexed_count = rag_service.index_startups(SKOLKOVO_DB, progress)
            print(f"✅ RAG индекс создан: {indexed_count} стартапов")
            
            # Сохраняем индекс
            rag_service.save_index(RAG_INDEX_FILE)
            print(f"✅ Индекс сохранен в {RAG_INDEX_FILE}")

async def main():
    await on_startup()
    await dp.start_polling(bot)
    await user_repository.on_end()

if __name__ == "__main__":
    asyncio.run(main())