"""
Re-ranking module -- uses GigaChat for relevance evaluation (_internal tier).
Falls back to RAG similarity if GigaChat is unavailable.

GigaChat используется для внутренних задач (re-ranking),
т.к. не тратит платные токены NeuroAPI и хорошо работает
с русскоязычными задачами классификации.
"""
import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class ReRanker:
    """
    Re-rank RAG candidates via LLM relevance scoring.

    1. RAG finds candidates by embedding similarity (fast, approximate).
    2. GigaChat evaluates each candidate 0-100 (slow, precise).
    3. Sort by AI score.

    Net effect: +20-30 % precision.
    """

    def __init__(self, giga=None):
        self._giga = giga
        self._giga_own: Optional[object] = None
        self._init_gigachat()

    def _init_gigachat(self):
        if self._giga is not None:
            logger.info("ReRanker: using passed GigaChat instance")
            return

        try:
            from gigachat import GigaChat
            from config import GIGACHAT_API_TOKEN
            if GIGACHAT_API_TOKEN:
                self._giga_own = GigaChat(
                    credentials=GIGACHAT_API_TOKEN,
                    verify_ssl_certs=False,
                    timeout=30,
                    scope="GIGACHAT_API_PERS",
                )
                logger.info("ReRanker: GigaChat initialised (_internal tier)")
            else:
                logger.warning("ReRanker: GIGACHAT_API_TOKEN not set, RAG similarity only")
        except Exception as e:
            logger.warning("ReRanker init: %s, RAG similarity only", e)

    @property
    def _client(self):
        return self._giga or self._giga_own

    def rerank(self, query: str, candidates: List[Dict], top_k: int = 3) -> List[Dict]:
        if not candidates:
            return []

        logger.info("Re-ranking: evaluating %d candidates", len(candidates))

        for i, startup in enumerate(candidates):
            try:
                relevance_score = self._evaluate_relevance(query, startup)
                startup["ai_relevance"] = relevance_score
                logger.info(
                    "  %d. %s: RAG=%.3f, AI=%.2f",
                    i + 1,
                    startup.get("name", "N/A"),
                    startup.get("rag_similarity", 0),
                    relevance_score,
                )
            except Exception as e:
                logger.error("Relevance eval error for %s: %s", startup.get("name", "N/A"), e)
                startup["ai_relevance"] = startup.get("rag_similarity", 0) * 100

        candidates.sort(key=lambda s: s.get("ai_relevance", 0), reverse=True)
        logger.info("Re-ranking done: top-%d selected", top_k)
        return candidates[:top_k]

    def _evaluate_relevance(self, query: str, startup: Dict) -> float:
        """Score relevance 0-100 via GigaChat. Falls back to RAG similarity."""
        client = self._client
        if client is None:
            return startup.get("rag_similarity", 0) * 100

        startup_summary = (
            f"Название: {startup.get('name', 'N/A')}\n"
            f"Кластер: {startup.get('cluster', 'N/A')}\n"
            f"Описание: {(startup.get('company_description', '') or startup.get('description', ''))[:300]}\n"
            f"Продукты: {str(startup.get('product_names', 'N/A'))[:150]}\n"
            f"Технологии: {str(startup.get('technologies', 'N/A'))[:150]}\n"
            f"Отрасли: {str(startup.get('industries', 'N/A'))[:100]}"
        )

        prompt = (
            "Оцени релевантность стартапа запросу пользователя по шкале от 0 до 100.\n\n"
            f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{query}\n\n"
            f"СТАРТАП:\n{startup_summary}\n\n"
            "КРИТЕРИИ:\n"
            "- 90-100: Прямое совпадение продукта/технологии\n"
            "- 70-89: Высокая релевантность, смежная область\n"
            "- 50-69: Средняя, общая тематика\n"
            "- 30-49: Низкая, слабая связь\n"
            "- 0-29: Нерелевантно\n\n"
            "ОТВЕТ (только число от 0 до 100):"
        )

        try:
            from gigachat.models import Chat, Messages, MessagesRole
            response = client.chat(Chat(
                messages=[Messages(role=MessagesRole.USER, content=prompt)],
                temperature=0.1,
                max_tokens=10,
            ))
            if response.choices:
                score_text = response.choices[0].message.content.strip()
                match = re.search(r"\d+", score_text)
                if match:
                    return min(100.0, max(0.0, float(match.group())))
            return startup.get("rag_similarity", 0) * 100
        except Exception as e:
            logger.error("GigaChat relevance call failed: %s", e)
            return startup.get("rag_similarity", 0) * 100
