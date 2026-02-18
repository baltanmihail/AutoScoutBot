"""
Universal LLM client -- uses NeuroAPI (OpenAI-compatible) for text generation.
GigaChat Embeddings are kept separately in services/rag_service.py.

Backward-compatible: class name and public interface unchanged.
"""

import json
import logging
import asyncio
from openai import OpenAI

from config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODELS,
    LLM_TOKEN_LIMITS,
    SYSTEM_PROMPT_PATH,
)

logger = logging.getLogger(__name__)


def _load_system_prompt():
    try:
        with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as file:
            return file.read()
    except Exception as e:
        logger.error(f"Ошибка загрузки system prompt: {e}")
        return "Ты - помощник для анализа стартапов. Форматируй ответ строго в JSON."


class GigaChatClient:
    """LLM client using NeuroAPI (OpenAI-compatible).
    Class name kept for backward compatibility with all imports."""

    def __init__(self, model_type: str = "standard"):
        self.model_type = model_type
        self.model_name = LLM_MODELS.get(model_type, LLM_MODELS.get("standard", "gemini-2.5-pro"))
        self.client: OpenAI | None = None
        self.system_prompt = _load_system_prompt()
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the OpenAI-compatible client for NeuroAPI."""
        try:
            logger.info(f"🔄 Инициализация LLM ({self.model_name}) через NeuroAPI")

            self.client = OpenAI(
                api_key=LLM_API_KEY,
                base_url=LLM_BASE_URL,
                timeout=60,
            )

            # Quick connectivity test
            test = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "Ответь одним словом: OK"}],
                max_tokens=5,
            )
            reply = test.choices[0].message.content.strip() if test.choices else "?"
            logger.info(f"✅ LLM клиент инициализирован: {self.model_name}")
            logger.info(f"📊 Тестовый ответ: {reply}")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации LLM ({self.model_name}): {e}")
            self.client = None

    def set_model(self, model_type: str):
        """Switch the active model tier."""
        self.model_type = model_type
        self.model_name = LLM_MODELS.get(model_type, LLM_MODELS.get("standard", "gemini-2.5-pro"))
        logger.info(f"🔄 Смена модели на: {self.model_name} (tier={model_type})")
        # No need to re-create client -- just change model name, same API key.

    # ------------------------------------------------------------------
    # generate_recommendation
    # ------------------------------------------------------------------

    def generate_recommendation(self, startup: dict, user_request: str = "", query_history=None) -> str:
        """Generate AI recommendation for a startup (standard and premium tiers)."""
        if not self.client:
            return ""

        limits = LLM_TOKEN_LIMITS.get(self.model_type, LLM_TOKEN_LIMITS.get("standard", {}))
        max_tokens = limits.get("recommendations", 0)
        if max_tokens <= 0:
            return ""

        try:
            few_shot_text = ""
            try:
                from services.few_shot_examples import get_few_shot_prompt
                history_patterns = []
                if query_history:
                    history_patterns = query_history.get_query_patterns(user_request)
                few_shot_text = get_few_shot_prompt(user_request, history_patterns)
                if few_shot_text:
                    logger.info("✅ Few-shot примеры добавлены в промпт")
            except Exception as e:
                logger.warning(f"⚠️ Few-shot примеры недоступны: {e}")

            startup_info = f"""
ОСНОВНАЯ ИНФОРМАЦИЯ:
Название: {startup.get('name', 'н/д')}
Кластер: {startup.get('cluster', 'н/д')}
Год основания: {startup.get('year', 'н/д')}
Статус: {startup.get('status', 'н/д')}

ОПИСАНИЕ:
{(startup.get('company_description', '') or startup.get('description', ''))[:400]}

ПРОДУКТЫ И ПРОЕКТЫ:
Продукты: {str(startup.get('product_names', 'н/д'))[:200]}
Проекты: {str(startup.get('project_names', 'н/д'))[:200]}
Технологии: {str(startup.get('technologies', 'н/д'))[:200]}
Отрасли применения: {str(startup.get('industries', 'н/д'))[:200]}

ТЕХНОЛОГИЧЕСКАЯ ЗРЕЛОСТЬ:
TRL: {startup.get('trl', 'н/д')}
IRL: {startup.get('irl', 'н/д')} - {str(startup.get('irl_description', ''))[:150]}
MRL: {startup.get('mrl', 'н/д')}
CRL: {startup.get('crl', 'н/д')} - {str(startup.get('crl_description', ''))[:150]}

ФИНАНСЫ:
Средняя прибыль: {startup.get('analysis', {}).get('AvgProfit', 0) / 1_000_000:.2f} млн руб
Динамика: {startup.get('analysis', {}).get('FinancialStability', 'н/д')}
Финансовое здоровье: {startup.get('analysis', {}).get('FinancialHealth', 'н/д')}

ПАТЕНТЫ И ИС:
Количество патентов: {startup.get('patent_count', 0)}
Детали: {str(startup.get('patents', 'Нет данных'))[:300]}
"""
            prompt = f"""Ты — ведущий отраслевой эксперт-аналитик. Проведи профессиональный анализ стартапа в контексте запроса.

{startup_info}

ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{user_request}
{few_shot_text}

ЗАДАЧА:
Проанализируй, насколько компания и её технологии соответствуют запросу. Дай экспертную оценку перспектив. Опирайся строго на факты из карточки стартапа.

СТРУКТУРА ОТВЕТА (без markdown, без **, без _):

Сильные стороны:
• [факт с цифрами или конкретными данными]
• [ещё факт — акцент на пересечении с запросом пользователя]

Риски:
• [конкретный риск с обоснованием]

Экспертная оценка:
[3-5 предложений. Объясни, чем компания может быть полезна в контексте запроса. Укажи технологические и коммерческие пересечения. Оцени потенциал развития в нужном направлении. Если прямого совпадения нет — объясни, в какой смежной области компания сильна.]

ПРАВИЛА:
- Фокус на ВОЗМОЖНОСТЯХ, а не на ограничениях
- Если нет прямого совпадения → "компания специализируется на смежном направлении", а не "не соответствует"
- Цифры: прибыль, выручка, TRL/IRL/MRL/CRL, количество патентов
- НЕ давай инвестиционные рекомендации
- НЕ используй markdown-разметку
- НЕ обрезай мысль на полуслове — заверши каждое предложение"""

            temperature = limits.get("temperature_recommendations", 0.5)

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            if response.choices:
                recommendation = response.choices[0].message.content.strip()
                recommendation = recommendation.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
                logger.info(f"✅ Сгенерирована рекомендация ({len(recommendation)} символов)")
                return recommendation

            return ""

        except Exception as e:
            logger.error(f"Ошибка генерации рекомендации: {e}")
            return ""

    # ------------------------------------------------------------------
    # get_startup_filters
    # ------------------------------------------------------------------

    def get_startup_filters(self, user_request: str, user_repository=None, user_id=None):
        """Convert user query into structured filters via LLM."""
        logger.info(f"📨 Запрос к LLM ({self.model_name}): {user_request}")

        limits = LLM_TOKEN_LIMITS.get(self.model_type, {})
        max_tokens = limits.get("filters", 0)

        # Some tiers skip LLM and use fallback (cheaper)
        if max_tokens <= 0 or not self.client:
            logger.info(f"🔄 Tier {self.model_type}: используем fallback-фильтры (RAG найдет релевантные)")
            fallback = self._get_fallback_filters(user_request)
            self._soften_filters(fallback)
            return fallback

        try:
            temperature = limits.get("temperature_filters", 0.2)

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_request},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            if not response.choices:
                logger.error("❌ Пустой ответ от LLM")
                return self._get_fallback_filters(user_request)

            json_string = response.choices[0].message.content
            logger.info(f"📥 Ответ LLM: {json_string}")

            json_string = self._clean_json_response(json_string)
            filters = json.loads(json_string)

            # Soften filters for economy/standard tiers
            if self.model_type in ("economy", "standard"):
                self._soften_filters(filters)

            filters = self._clean_empty_filters(filters, user_request)

            if not self._validate_filters(filters):
                logger.error("❌ Невалидная структура фильтров")
                return self._get_fallback_filters(user_request)

            # Token tracking
            tokens_used = 0
            if hasattr(response, "usage") and response.usage:
                tokens_used = response.usage.total_tokens
            logger.info(f"✅ Фильтры получены ({self.model_name}), токенов: {tokens_used}")

            if user_repository and user_id and tokens_used > 0:
                try:
                    asyncio.create_task(
                        user_repository.add_token_usage(user_id, self.model_type, tokens_used, user_request[:200])
                    )
                except Exception as e:
                    logger.error(f"Ошибка сохранения токенов: {e}")

            return filters

        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка JSON: {e}")
            return self._get_fallback_filters(user_request)
        except Exception as e:
            logger.error(f"❌ Ошибка LLM: {e}")
            return self._get_fallback_filters(user_request)

    # ------------------------------------------------------------------
    # Helpers (unchanged logic, just cleaned up)
    # ------------------------------------------------------------------

    @staticmethod
    def _soften_filters(filters: dict):
        """Remove strict criteria so RAG can find relevant startups."""
        for key in ("DeepTech", "GenAI", "WOW"):
            filters[key] = ""
        for key in ("trl", "irl", "mrl", "crl", "stage", "cluster", "category"):
            filters[key] = []
        filters["min_profit"] = 0

    @staticmethod
    def _clean_json_response(json_string: str) -> str:
        json_string = json_string.replace("```json", "").replace("```", "").strip()
        json_string = " ".join(json_string.split())
        return json_string

    def _clean_empty_filters(self, filters: dict, user_request: str) -> dict:
        fallback = self._get_fallback_filters(user_request)
        if not filters.get("DeepTech"):
            filters["DeepTech"] = fallback["DeepTech"]
        if not filters.get("GenAI"):
            filters["GenAI"] = fallback["GenAI"]
        if not filters.get("WOW"):
            filters["WOW"] = fallback["WOW"]
        for key in ("trl", "irl", "mrl", "crl", "year", "country", "category", "stage", "cluster", "status"):
            if not filters.get(key):
                filters[key] = fallback.get(key, [])
        if "min_profit" not in filters or filters.get("min_profit") is None:
            filters["min_profit"] = fallback.get("min_profit", 0)
        if "has_patents" not in filters:
            filters["has_patents"] = fallback.get("has_patents", False)
        return filters

    @staticmethod
    def _validate_filters(filters: dict) -> bool:
        required = {"DeepTech", "GenAI", "WOW", "trl", "irl", "mrl", "crl", "year", "country", "category", "stage", "min_profit"}
        if not isinstance(filters, dict):
            return False
        missing = required - filters.keys()
        if missing:
            logger.error(f"❌ Отсутствуют ключи: {missing}")
            return False
        dt = filters.get("DeepTech")
        if dt != "" and not isinstance(dt, (int, str)):
            return False
        if isinstance(dt, str) and dt != "" and not dt.isdigit():
            return False
        if filters.get("GenAI") not in ("есть", "нет", ""):
            return False
        if filters.get("WOW") not in ("да", "нет", ""):
            return False
        if not isinstance(filters.get("min_profit"), (int, float)):
            return False
        return True

    def _get_fallback_filters(self, user_request: str = ""):
        """Smart keyword-based fallback filters."""
        logger.info("🔄 Используются адаптивные fallback-фильтры")
        q = user_request.lower()

        is_bad = any(w in q for w in ("плохой", "слабый", "низкий", "плох"))
        is_good = any(w in q for w in ("хороший", "сильный", "высокий", "лучш", "перспектив"))

        min_profit = 0
        for phrase, val in [
            ("более 100 млн", 100_000_000), ("больше 100 млн", 100_000_000),
            ("более 50 млн", 50_000_000), ("больше 50 млн", 50_000_000),
            ("более 10 млн", 10_000_000), ("больше 10 млн", 10_000_000),
            ("более 5 млн", 5_000_000), ("более 1 млн", 1_000_000), ("прибыльн", 1_000_000),
        ]:
            if phrase in q:
                min_profit = val
                break

        cluster, category, country = [], [], []
        for kw_list, val in [
            (("ит", "it", "софт", "программ", "digital", "цифров"), ["ИТ"]),
            (("биомед", "медицин", "здравоохран", "фарм"), ["Биомедицина"]),
            (("энерг", "энерготех"), ["Энерготех"]),
        ]:
            if any(w in q for w in kw_list):
                cluster = val
                break
        for kw_list, val in [
            (("ит", "it", "софт", "программ"), ["ИНФОРМАЦИОННЫЕ ТЕХНОЛОГИИ"]),
            (("медицин", "здравоохран", "фарм", "биомед"), ["ЗДРАВООХРАНЕНИЕ"]),
            (("финанс", "финтех", "банк"), ["ФИНАНСОВЫЙ СЕКТОР"]),
            (("промышл", "производств"), ["ПРОМЫШЛЕННОСТЬ"]),
        ]:
            if any(w in q for w in kw_list):
                category = val
                break
        for kw, val in [("санкт-петербург", "Санкт-Петербург"), ("спб", "Санкт-Петербург"),
                        ("москв", "Москва"), ("екатеринбург", "Екатеринбург")]:
            if kw in q:
                country = [val]
                break

        has_patents = None
        if any(w in q for w in ("патент", "защищен", "интеллектуальн")):
            has_patents = True

        keyword_search = ""
        if not category:
            exclude = {"проект", "связанный", "годовой", "прибылью", "более", "млн", "руб", "стартап", "компания"}
            words = [w for w in q.split() if len(w) > 4 and w not in exclude]
            keyword_search = " ".join(words[:3])

        if is_bad:
            return {"DeepTech": 1, "GenAI": "нет", "WOW": "нет",
                    "trl": ["1-3"], "irl": ["1-3"], "mrl": ["1-3"], "crl": ["1-3"],
                    "year": ["2015-2025"], "country": country, "category": category,
                    "cluster": cluster, "stage": [], "status": ["active"],
                    "min_profit": min_profit, "has_patents": has_patents, "keyword_search": keyword_search}
        if is_good:
            return {"DeepTech": 3, "GenAI": "есть", "WOW": "да",
                    "trl": ["7-9"], "irl": ["7-9"], "mrl": ["7-9"], "crl": ["7-9"],
                    "year": ["2018-2025"], "country": country, "category": category,
                    "cluster": cluster, "stage": [], "status": ["active"],
                    "min_profit": min_profit, "has_patents": has_patents, "keyword_search": keyword_search}

        return {"DeepTech": "", "GenAI": "", "WOW": "",
                "trl": [], "irl": [], "mrl": [], "crl": [],
                "year": [], "country": country, "category": category,
                "cluster": cluster, "stage": [], "status": ["active"],
                "min_profit": min_profit, "has_patents": has_patents, "keyword_search": keyword_search}
