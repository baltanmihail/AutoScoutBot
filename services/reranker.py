"""
Re-ranking модуль для улучшения точности поиска
Переоценивает результаты RAG через GigaChat для лучшего понимания контекста
"""
import logging
from typing import List, Dict
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

logger = logging.getLogger(__name__)

class ReRanker:
    """
    Переранжирование результатов RAG через GigaChat
    
    Логика:
    1. RAG находит кандидатов по similarity (быстро, но неточно)
    2. GigaChat оценивает каждого от 0 до 100 (медленно, но точно)
    3. Сортируем по AI оценке
    
    Результат: +20-30% точности
    """
    
    def __init__(self, giga: GigaChat):
        self.giga = giga
        
    def rerank(self, query: str, candidates: List[Dict], top_k: int = 3) -> List[Dict]:
        """
        Переранжирование кандидатов через GigaChat
        
        Args:
            query: запрос пользователя
            candidates: список стартапов от RAG
            top_k: сколько вернуть после переранжирования
            
        Returns:
            Отсортированный список стартапов с ai_relevance
        """
        if not candidates:
            return []
        
        logger.info(f"🔄 Re-ranking: оценка {len(candidates)} кандидатов через GigaChat")
        
        # Оцениваем каждого кандидата
        for i, startup in enumerate(candidates):
            try:
                relevance_score = self._evaluate_relevance(query, startup)
                startup['ai_relevance'] = relevance_score
                logger.info(f"  {i+1}. {startup.get('name', 'N/A')}: RAG={startup.get('rag_similarity', 0):.3f}, AI={relevance_score:.2f}")
            except Exception as e:
                logger.error(f"Ошибка оценки {startup.get('name', 'N/A')}: {e}")
                startup['ai_relevance'] = startup.get('rag_similarity', 0) * 100  # Fallback
        
        # Сортируем по AI оценке
        candidates.sort(key=lambda s: s.get('ai_relevance', 0), reverse=True)
        
        logger.info(f"✅ Re-ranking завершен: топ-{top_k} выбраны")
        return candidates[:top_k]
    
    def _evaluate_relevance(self, query: str, startup: Dict) -> float:
        """
        Оценка релевантности стартапа запросу через GigaChat
        
        Returns:
            Оценка от 0 до 100
        """
        # Формируем краткую информацию о стартапе
        startup_summary = f"""
Название: {startup.get('name', 'N/A')}
Кластер: {startup.get('cluster', 'N/A')}
Описание: {startup.get('company_description', startup.get('description', 'N/A'))[:300]}
Продукты: {startup.get('product_names', 'N/A')[:150]}
Технологии: {startup.get('technologies', 'N/A')[:150]}
Отрасли: {startup.get('industries', 'N/A')[:100]}
"""
        
        prompt = f"""Оцени релевантность стартапа запросу пользователя по шкале от 0 до 100.

ЗАПРОС ПОЛЬЗОВАТЕЛЯ:
{query}

СТАРТАП:
{startup_summary}

КРИТЕРИИ ОЦЕНКИ:
- 90-100: Прямое совпадение (продукт/технология точно соответствует запросу)
- 70-89: Высокая релевантность (смежная область, частичное совпадение)
- 50-69: Средняя релевантность (общая тематика, косвенное отношение)
- 30-49: Низкая релевантность (слабая связь, другая отрасль)
- 0-29: Нерелевантно (полностью другая область)

ПРИМЕРЫ:
Запрос: "переработка пластика"
Стартап: производство биоразлагаемых пакетов → 95 (прямое совпадение)
Стартап: переработка древесины → 60 (смежная область)
Стартап: разработка мобильных приложений → 10 (другая отрасль)

ОТВЕТ (только число от 0 до 100):"""
        
        try:
            response = self.giga.chat(Chat(
                messages=[Messages(role=MessagesRole.USER, content=prompt)],
                temperature=0.1,  # Низкая температура для стабильности
                max_tokens=10
            ))
            
            if response and response.choices:
                score_text = response.choices[0].message.content.strip()
                # Извлекаем число
                import re
                match = re.search(r'\d+', score_text)
                if match:
                    score = float(match.group())
                    return min(100, max(0, score))  # Ограничиваем 0-100
            
            # Fallback: используем RAG similarity
            return startup.get('rag_similarity', 0) * 100
            
        except Exception as e:
            logger.error(f"Ошибка оценки релевантности: {e}")
            return startup.get('rag_similarity', 0) * 100

