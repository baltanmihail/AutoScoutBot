import json
import logging
import asyncio
from config import GIGACHAT_API_TOKEN, GIGACHAT_TOKEN_LIMITS, SYSTEM_PROMPT_PATH, GIGACHAT_MODELS
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

logger = logging.getLogger(__name__)

def _load_system_prompt():
    try:
        with open(SYSTEM_PROMPT_PATH, "r", encoding='utf-8') as file:
            system_prompt_text = file.read()
            return system_prompt_text
    except Exception as e:
        logger.error(f"Ошибка загрузки system prompt: {e}")
        return "Ты - помощник для анализа стартапов. Форматируй ответ строго в JSON."

class GigaChatClient:
    def __init__(self, model_type: str = "standard"):
        self.model_type = model_type
        self.model_name = GIGACHAT_MODELS.get(model_type, "GigaChat")
        self.giga = None
        self.system_prompt = _load_system_prompt()
        
        self._initialize_client()
        
    def _initialize_client(self):
        """Инициализация клиента GigaChat с обработкой ошибок"""
        try:
            logger.info(f"🔄 Инициализация GigaChat с моделью: {self.model_name}")
            
            self.giga = GigaChat(
                credentials=GIGACHAT_API_TOKEN,  
                scope="GIGACHAT_API_PERS",          
                model=self.model_name,
                verify_ssl_certs=False,
                timeout=30  # Увеличиваем таймаут
            )
            
            # Тестовый запрос для проверки соединения
            test_payload = Chat(
                messages=[
                    Messages(role=MessagesRole.SYSTEM, content="Тест"),
                    Messages(role=MessagesRole.USER, content="Ответь 'OK'"),
                ]
            )
            
            test_response = self.giga.chat(payload=test_payload)
            logger.info(f"✅ GigaChat клиент успешно инициализирован с моделью {self.model_name}")
            logger.info(f"📊 Тестовый ответ: {test_response.choices[0].message.content}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации GigaChat с моделью {self.model_name}: {e}")
            self.giga = None
        
    def set_model(self, model_type: str):
        """Изменение модели GigaChat"""
        self.model_type = model_type
        self.model_name = GIGACHAT_MODELS.get(model_type, "GigaChat")
        logger.info(f"🔄 Смена модели на: {self.model_name}")
        self._initialize_client()
    
    def generate_recommendation(self, startup: dict, user_request: str = "", query_history=None) -> str:
        """
        Генерация AI-рекомендации для стартапа (для моделей Pro и Max)
        С few-shot learning для повышения точности
        
        Pro: более краткий анализ (500 токенов)
        Max: глубокий анализ с максимальной детализацией (250 токенов)
        """
        if self.model_type not in ["pro", "max"] or not self.giga:
            return ""
        
        try:
            # Получаем few-shot примеры
            few_shot_text = ""
            try:
                from services.few_shot_examples import get_few_shot_prompt
                
                # Получаем паттерны из истории
                history_patterns = []
                if query_history:
                    history_patterns = query_history.get_query_patterns(user_request)
                
                # Генерируем few-shot промпт
                few_shot_text = get_few_shot_prompt(user_request, history_patterns)
                if few_shot_text:
                    logger.info(f"✅ Few-shot примеры добавлены в промпт")
            except Exception as e:
                logger.warning(f"⚠️ Few-shot примеры недоступны: {e}")
            # Формируем ПОЛНУЮ информацию о стартапе для глубокого анализа
            startup_info = f"""
ОСНОВНАЯ ИНФОРМАЦИЯ:
Название: {startup.get('name', 'н/д')}
Кластер: {startup.get('cluster', 'н/д')}
Год основания: {startup.get('year', 'н/д')}
Статус: {startup.get('status', 'н/д')}

ОПИСАНИЕ:
{startup.get('company_description', startup.get('description', 'н/д'))[:400]}

ПРОДУКТЫ И ПРОЕКТЫ:
Продукты: {startup.get('product_names', 'н/д')[:200]}
Проекты: {startup.get('project_names', 'н/д')[:200]}
Технологии: {startup.get('technologies', 'н/д')[:200]}
Отрасли применения: {startup.get('industries', 'н/д')[:200]}

ТЕХНОЛОГИЧЕСКАЯ ЗРЕЛОСТЬ:
TRL: {startup.get('trl', 'н/д')}
IRL: {startup.get('irl', 'н/д')} - {startup.get('irl_description', '')[:150]}
MRL: {startup.get('mrl', 'н/д')}
CRL: {startup.get('crl', 'н/д')} - {startup.get('crl_description', '')[:150]}

ФИНАНСЫ:
Средняя прибыль: {startup.get('analysis', {}).get('AvgProfit', 0) / 1_000_000:.2f} млн руб
Максимальная прибыль: {startup.get('analysis', {}).get('AvgProfit', 0) / 1_000_000:.2f} млн руб
Динамика: {startup.get('analysis', {}).get('FinancialStability', 'н/д')}
Финансовое здоровье: {startup.get('analysis', {}).get('FinancialHealth', 'н/д')}

ПАТЕНТЫ И ИС:
Количество патентов: {startup.get('patent_count', 0)}
Количество товарных знаков: {startup.get('trademark_count', 0)}
Детали: {startup.get('patents', 'Нет данных')[:300]}
"""
            
            prompt = f"""Ты - опытный отраслевой эксперт-аналитик. Проведи профессиональный анализ стартапа в контексте запроса пользователя.

{startup_info}

ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{user_request}
{few_shot_text}

ЗАДАЧА:
Как эксперт отрасли, оцени перспективы компании в контексте запроса пользователя. Используй профессиональный консультативный тон.

ФОРМАТ ОТВЕТА (строго БЕЗ MARKDOWN):

Сильные стороны:
• [конкретный факт с цифрами, АКЦЕНТ НА СОВПАДЕНИЯ с запросом]
• [конкретный факт с цифрами, АКЦЕНТ НА СОВПАДЕНИЯ с запросом]
• [конкретный факт с цифрами, АКЦЕНТ НА СОВПАДЕНИЯ с запросом]

Риски:
• [конкретный риск с обоснованием, но БЕЗ прямых фраз "не соответствует"]
• [конкретный риск с обоснованием, но БЕЗ прямых фраз "не соответствует"]

Экспертная оценка:
[2-3 предложения: какие аспекты деятельности компании пересекаются с запросом, технологические и коммерческие перспективы, возможности адаптации/развития в нужном направлении. Фокус на ВОЗМОЖНОСТЯХ, а не на ограничениях.]

КРИТИЧЕСКИ ВАЖНО:
- ПЕРВЫМ делом найди и выдели СОВПАДЕНИЯ между продуктом/технологией компании и запросом пользователя
- Если есть частичное совпадение (например, переработка отходов → clean tech) - ПОДЧЕРКНИ это в сильных сторонах
- Не пиши прямо "не соответствует запросу" - используй смягченные формулировки: "специализируется на смежной области", "частично покрывает запрос", "фокус на другом сегменте"
- Используй профессиональный консультативный язык (как отраслевой эксперт для клиента)
- Опирайся на КОНКРЕТНЫЕ данные (прибыль, патенты {startup.get('patent_count', 0)} шт, TRL/IRL, технологии, продукты)
- НЕ давай инвестиционные рекомендации, советы по инвестированию, суммы инвестиций, ROI
- НЕ используй markdown (**, __, *, _)
- Акцент на ВОЗМОЖНОСТИ и СОВПАДЕНИЯ, а не на несоответствия"""

            # Параметры берем из конфига (настраиваемые)
            limits = GIGACHAT_TOKEN_LIMITS.get(self.model_type, GIGACHAT_TOKEN_LIMITS["max"])
            max_tokens = limits["recommendations"]
            temperature = limits["temperature_recommendations"]
            
            payload = Chat(
                messages=[
                    Messages(role=MessagesRole.USER, content=prompt),
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            response = self.giga.chat(payload=payload)
            
            if response.choices:
                recommendation = response.choices[0].message.content.strip()
                # Убираем markdown форматирование
                recommendation = recommendation.replace('**', '').replace('__', '').replace('*', '').replace('_', '')
                logger.info(f"✅ Сгенерирована рекомендация ({len(recommendation)} символов)")
                return recommendation
            
            return ""
            
        except Exception as e:
            logger.error(f"Ошибка генерации рекомендации: {e}")
            return ""
        
    def get_startup_filters(self, user_request: str, user_repository=None, user_id=None):
        """Получение фильтров с улучшенной обработкой ошибок"""
        logger.info(f"📨 Запрос к GigaChat ({self.model_name}): {user_request}")
        
        # Pro использует МЯГКИЙ fallback (RAG найдет релевантные)
        if self.model_type == "pro":
            logger.info(f"🔄 Модель Pro: используем МЯГКИЙ поиск (RAG найдет релевантные)")
            fallback = self._get_fallback_filters(user_request)
            
            # Убираем строгие фильтры для RAG
            fallback["DeepTech"] = ""
            fallback["GenAI"] = ""
            fallback["WOW"] = ""
            fallback["trl"] = []
            fallback["irl"] = []
            fallback["mrl"] = []
            fallback["crl"] = []
            fallback["stage"] = []
            fallback["cluster"] = []
            fallback["category"] = []
            fallback["min_profit"] = 0
            
            logger.info("🎯 Для Pro: убраны строгие фильтры, RAG сам найдет релевантные")
            return fallback
        
        if not self.giga:
            logger.error("❌ GigaChat клиент не инициализирован")
            return self._get_fallback_filters(user_request)
            
        try:
            # Параметры берем из конфига (настраиваемые)
            limits = GIGACHAT_TOKEN_LIMITS.get(self.model_type, GIGACHAT_TOKEN_LIMITS["max"])
            max_tokens = limits["filters"]
            temperature = limits["temperature_filters"]
            
            payload = Chat(
                messages=[
                    Messages(role=MessagesRole.SYSTEM, content=self.system_prompt),
                    Messages(role=MessagesRole.USER, content=user_request),
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            logger.info("🔄 Отправка запроса к GigaChat API...")
            response = self.giga.chat(payload=payload)
            
            if not response.choices:
                logger.error("❌ Пустой ответ от GigaChat")
                return self._get_fallback_filters(user_request)
                
            json_string = response.choices[0].message.content
            logger.info(f"📥 Получен ответ от GigaChat: {json_string}")
            
            # Очистка ответа от возможных markdown-форматирования
            json_string = self._clean_json_response(json_string)
            
            # Парсинг JSON
            filters = json.loads(json_string)
            
            # Для Standard: МЯГКИЕ фильтры (RAG сам найдет релевантные)
            if self.model_type == "standard":
                # Убираем строгие фильтры, оставляем только критичные
                filters["DeepTech"] = ""
                filters["GenAI"] = ""
                filters["WOW"] = ""
                filters["trl"] = []
                filters["irl"] = []
                filters["mrl"] = []
                filters["crl"] = []
                filters["stage"] = []
                filters["cluster"] = []
                filters["category"] = []
                filters["min_profit"] = 0
                logger.info("🎯 Для Standard: убраны строгие фильтры, RAG сам найдет релевантные")
            
            # Для Max: ослабляем фильтры по stage
            elif self.model_type == "max":
                filters["stage"] = []
                logger.info("🎯 Для Max: убраны ограничения по стадии (RAG найдет лучшие)")
            
            filters = self._clean_empty_filters(filters, user_request)
            
            # Валидация структуры фильтров
            if not self._validate_filters(filters):
                logger.error("❌ Невалидная структура фильтров от GigaChat")
                return self._get_fallback_filters(user_request)
            
            # Получаем информацию о токенах
            tokens_used = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
            logger.info(f"✅ Успешно получены фильтры от GigaChat ({self.model_name})")
            logger.info(f"💰 Использовано токенов: {tokens_used}")
            
            # Сохраняем информацию о токенах в базу
            if user_repository and user_id and tokens_used > 0:
                try:
                    asyncio.create_task(
                        user_repository.add_token_usage(user_id, self.model_type, tokens_used, user_request[:200])
                    )
                except Exception as e:
                    logger.error(f"Ошибка сохранения токенов: {e}")
            
            return filters
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка декодирования JSON от GigaChat: {e}")
            logger.error(f"📄 Полученный текст: {json_string}")
            return self._get_fallback_filters(user_request)
            
        except Exception as e:
            logger.error(f"❌ Ошибка GigaChat: {e}")
            return self._get_fallback_filters(user_request)
    
    def _clean_json_response(self, json_string: str) -> str:
        """Очистка JSON ответа от возможного markdown-форматирования"""
        # Удаляем markdown коды ```json и ```
        json_string = json_string.replace('```json', '').replace('```', '').strip()
        
        # Удаляем лишние пробелы и переносы
        json_string = ' '.join(json_string.split())
        
        return json_string
    
    def _clean_empty_filters(self, filters: dict, user_request: str) -> dict:
        """Заменяем пустые значения на разумные defaults"""
        fallback = self._get_fallback_filters(user_request)
        
        # Заменяем пустые строки на значения из fallback
        if not filters.get("DeepTech") or filters.get("DeepTech") == "":
            filters["DeepTech"] = fallback["DeepTech"]
            logger.info(f"Заменен пустой DeepTech на {fallback['DeepTech']}")
        
        if not filters.get("GenAI") or filters.get("GenAI") == "":
            filters["GenAI"] = fallback["GenAI"]
            logger.info(f"Заменен пустой GenAI на {fallback['GenAI']}")
        
        if not filters.get("WOW") or filters.get("WOW") == "":
            filters["WOW"] = fallback["WOW"]
            logger.info(f"Заменен пустой WOW на {fallback['WOW']}")
        
        # Для списков - заменяем пустые на fallback
        for key in ["trl", "irl", "mrl", "crl", "year", "country", "category", "stage", "cluster", "status"]:
            if not filters.get(key) or filters.get(key) == "" or (isinstance(filters.get(key), list) and len(filters.get(key)) == 0):
                filters[key] = fallback.get(key, [])
                if filters[key]:
                    logger.info(f"Заменен пустой {key} на {fallback.get(key, [])}")
        
        # Для min_profit
        if "min_profit" not in filters or filters.get("min_profit") is None:
            filters["min_profit"] = fallback.get("min_profit", 0)
        
        # Для has_patents
        if "has_patents" not in filters:
            filters["has_patents"] = fallback.get("has_patents", False)
        
        return filters
    
    def _validate_filters(self, filters: dict) -> bool:
        """Валидация структуры фильтров"""
        required_keys = {"DeepTech", "GenAI", "WOW", "trl", "irl", "mrl", "crl", "year", "country", "category", "stage", "min_profit"}
        
        if not isinstance(filters, dict):
            return False
            
        missing_keys = required_keys - filters.keys()
        if missing_keys:
            logger.error(f"❌ Отсутствуют обязательные ключи: {missing_keys}")
            return False
            
        # Проверяем типы значений (допускаем пустые строки)
        deeptech = filters.get("DeepTech")
        if deeptech != "" and not isinstance(deeptech, (int, str)):
            logger.error(f"❌ Неверный тип DeepTech: {type(deeptech)}")
            return False
        
        # Если DeepTech - строка, проверяем что это число или пустая строка
        if isinstance(deeptech, str) and deeptech != "" and not deeptech.isdigit():
            logger.error(f"❌ DeepTech должен быть числом или пустой строкой: {deeptech}")
            return False
            
        if filters.get("GenAI") not in ["есть", "нет", ""]:
            logger.error(f"❌ Неверное значение GenAI: {filters.get('GenAI')}")
            return False
        if filters.get("WOW") not in ["да", "нет", ""]:
            logger.error(f"❌ Неверное значение WOW: {filters.get('WOW')}")
            return False
        
        # Проверяем min_profit
        min_profit = filters.get("min_profit")
        if not isinstance(min_profit, (int, float)):
            logger.error(f"❌ min_profit должен быть числом: {min_profit}")
            return False
            
        return True
    
    def _get_fallback_filters(self, user_request: str = ""):
        """Умные fallback-фильтры на основе запроса пользователя"""
        logger.info("🔄 Используются адаптивные fallback-фильтры")
        
        user_request_lower = user_request.lower()
        
        # Определяем, какой тип стартапа ищет пользователь
        is_bad_startup = any(word in user_request_lower for word in ["плохой", "слабый", "низкий", "плох"])
        is_good_startup = any(word in user_request_lower for word in ["хороший", "сильный", "высокий", "лучш", "перспектив"])
        is_just_startup = "стартап" in user_request_lower and not is_good_startup and not is_bad_startup
        
        # Определяем максимальную прибыль для "стартапов" (не зрелых компаний)
        max_profit_limit = None
        if is_just_startup:
            # Если ищут именно стартап - ограничиваем прибыль до 20 млн
            # (больше = уже средний/крупный бизнес, не стартап)
            max_profit_limit = 20_000_000
            logger.info("🎯 Поиск стартапов: ограничение прибыли до 20 млн (исключаем зрелые компании)")
        
        # Определяем прибыль (более точный парсинг)
        min_profit = 0
        if any(phrase in user_request_lower for phrase in ["более 100 млн", "больше 100 млн", "свыше 100 млн"]):
            min_profit = 100000000
        elif any(phrase in user_request_lower for phrase in ["более 50 млн", "больше 50 млн", "свыше 50 млн"]):
            min_profit = 50000000
        elif any(phrase in user_request_lower for phrase in ["более 10 млн", "больше 10 млн", "свыше 10 млн"]):
            min_profit = 10000000
        elif any(phrase in user_request_lower for phrase in ["более 5 млн", "больше 5 млн", "свыше 5 млн"]):
            min_profit = 5000000
        elif any(phrase in user_request_lower for phrase in ["более 1 млн", "больше 1 млн", "свыше 1 млн", "прибыльн"]):
            min_profit = 1000000
        
        # Определяем кластер (более точно чем category)
        cluster = []
        if any(word in user_request_lower for word in ["ит", "it", "информационн", "софт", "программ", "digital", "цифров"]):
            cluster = ["ИТ"]
        elif any(word in user_request_lower for word in ["биомед", "медицин", "здравоохран", "health", "фарм"]):
            cluster = ["Биомедицина"]
        elif any(word in user_request_lower for word in ["энерг", "энерготех", "energy"]):
            cluster = ["Энерготех"]
        
        # Определяем категорию (только если уверены, иначе оставляем пустым для поиска по ключевым словам)
        category = []
        if any(word in user_request_lower for word in ["ит", "it", "информационн", "софт", "программ", "digital", "цифров"]):
            category = ["ИНФОРМАЦИОННЫЕ ТЕХНОЛОГИИ"]
        elif any(word in user_request_lower for word in ["медицин", "здравоохран", "health", "фарм", "биомед"]):
            category = ["ЗДРАВООХРАНЕНИЕ"]
        elif any(word in user_request_lower for word in ["финанс", "финтех", "fintech", "банк"]):
            category = ["ФИНАНСОВЫЙ СЕКТОР"]
        elif any(word in user_request_lower for word in ["промышл", "производств", "завод", "машиностроен"]):
            category = ["ПРОМЫШЛЕННОСТЬ"]
        elif any(word in user_request_lower for word in ["строител", "construction"]):
            category = ["СТРОИТЕЛЬСТВО"]
        elif any(word in user_request_lower for word in ["торговл", "retail", "магазин"]):
            category = ["ТОРГОВЛЯ"]
        
        # Для остальных (логистика, образование и т.д.) добавляем поиск по ключевым словам
        keyword_search = ""
        if not category:
            # Извлекаем ключевые слова из запроса для поиска
            # Исключаем служебные слова
            exclude_words = ["проект", "связанный", "годовой", "прибылью", "более", "млн", "руб", "стартап", "компания"]
            words = [w for w in user_request_lower.split() if len(w) > 4 and w not in exclude_words]
            if words:
                keyword_search = " ".join(words[:3])  # Берем первые 3 значимых слова
        
        # Определяем регион
        country = []
        if "санкт-петербург" in user_request_lower or "спб" in user_request_lower or "петербург" in user_request_lower:
            country = ["Санкт-Петербург"]
        elif "москв" in user_request_lower:
            country = ["Москва"]
        elif "екатеринбург" in user_request_lower:
            country = ["Екатеринбург"]
        elif "новосибирск" in user_request_lower:
            country = ["Новосибирск"]
        
        # Определяем стадию - НЕ ограничиваем, RAG сам найдет лучшие
        stage = []
        
        # Статус (по умолчанию только активные - в базе это "active")
        status = ["active"]
        
        # Патенты - ТОЛЬКО если явно упомянуты, иначе None (не фильтруем)
        has_patents = None
        if any(word in user_request_lower for word in ["патент", "защищен", "интеллектуальн"]):
            has_patents = True
        elif any(word in user_request_lower for word in ["без патент", "не патент"]):
            has_patents = False
        
        # Базовые фильтры в зависимости от запроса
        if is_bad_startup:
            filters = {
                "DeepTech": 1,
                "GenAI": "нет", 
                "WOW": "нет",
                "trl": ["1-3"],
                "irl": ["1-3"],
                "mrl": ["1-3"],
                "crl": ["1-3"],
                "year": ["2015-2025"],
                "country": country,
                "category": category,
                "cluster": cluster,
                "stage": stage,
                "status": status,
                "min_profit": min_profit,
                "has_patents": has_patents,
                "keyword_search": keyword_search
            }
            logger.info("🔧 Настроены фильтры для плохих/слабых стартапов")
        elif is_good_startup:
            filters = {
                "DeepTech": 3,
                "GenAI": "есть", 
                "WOW": "да",
                "trl": ["7-9"],
                "irl": ["7-9"],
                "mrl": ["7-9"],
                "crl": ["7-9"],
                "year": ["2018-2025"],
                "country": country,
                "category": category,
                "cluster": cluster,
                "stage": stage,
                "status": status,
                "min_profit": min_profit,
                "has_patents": has_patents,
                "keyword_search": keyword_search
            }
            logger.info("🔧 Настроены фильтры для хороших/сильных стартапов")
        else:
            # Мягкие фильтры для широкого поиска (RAG сам найдет релевантные)
            filters = {
                "DeepTech": "",
                "GenAI": "",
                "WOW": "",
                "trl": [],
                "irl": [],
                "mrl": [],
                "crl": [],
                "year": [],
                "country": country,
                "category": category,
                "cluster": cluster,
                "stage": [],  # Убираем ограничение по стадии - RAG сам найдет лучшие
                "status": status,
                "min_profit": min_profit,
                "max_profit_limit": max_profit_limit,  # Ограничение сверху для стартапов
                "has_patents": has_patents,
                "keyword_search": keyword_search
            }
            logger.info("🔧 Настроены мягкие фильтры для широкого поиска (RAG найдет лучшие)")
        
        logger.info(f"🎯 Используемые фильтры: {filters}")
        return filters