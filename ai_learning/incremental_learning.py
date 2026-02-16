"""
Инкрементальное обучение - обучение после каждого запроса
Легкое и быстрое обновление знаний без полного анализа
"""
import logging
import sqlite3
from typing import Dict, List
from collections import defaultdict

logger = logging.getLogger(__name__)

class IncrementalLearner:
    """
    Инкрементальное обучение после каждого запроса
    
    В отличие от полного обучения (Self Learning Engine):
    - Работает БЫСТРО (< 1 секунды)
    - Обновляет только последний запрос
    - Не генерирует файлы
    - Обновляет счетчики и статистику в БД
    
    Полное обучение запускается каждые N запросов для:
    - Генерации few-shot примеров
    - Создания синонимов
    - Экспорта для fine-tuning
    """
    
    def __init__(self, db_path: str = "query_history.db"):
        self.db_path = db_path
        
        # Загружаем настройки
        try:
            from config import SELF_LEARNING
            self.min_ai_relevance = SELF_LEARNING.get('min_ai_relevance', 80)
        except ImportError:
            self.min_ai_relevance = 80
    
    def learn_from_query(self, query_id: int) -> Dict:
        """
        Быстрое обучение на основе одного запроса
        
        Args:
            query_id: ID запроса из query_history.db
            
        Returns:
            Отчет о проделанной работе
        """
        report = {
            "patterns_updated": 0,
            "insights_gained": [],
            "quality_assessment": "",
        }
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Получаем информацию о запросе
            cursor.execute("""
                SELECT query_text, model_type, expanded_query
                FROM queries
                WHERE id = ?
            """, (query_id,))
            
            query_row = cursor.fetchone()
            if not query_row:
                return report
            
            query_text, model_type, expanded_query = query_row
            
            # Получаем результаты
            cursor.execute("""
                SELECT startup_name, cluster, technologies, 
                       rag_similarity, ai_relevance
                FROM query_results
                WHERE query_id = ?
                ORDER BY ai_relevance DESC
            """, (query_id,))
            
            results = cursor.fetchall()
            
            if not results:
                return report
            
            # Анализируем результаты
            avg_relevance = sum(r[4] or 0 for r in results) / len(results)
            best_relevance = max(r[4] or 0 for r in results)
            
            # Определяем успешность запроса
            if best_relevance >= self.min_ai_relevance:
                # Успешный запрос - обновляем/создаем паттерн
                self._update_pattern_incremental(
                    cursor, query_text, results, avg_relevance
                )
                report["patterns_updated"] = 1
                report["quality_assessment"] = "✅ Отличный результат"
                report["insights_gained"].append(
                    f"Запрос '{query_text[:50]}...' дал хорошие результаты (AI={best_relevance:.0f})"
                )
            elif avg_relevance >= 60:
                report["quality_assessment"] = "🟡 Средний результат"
                report["insights_gained"].append(
                    f"Запрос можно улучшить: средняя релевантность {avg_relevance:.0f}/100"
                )
            else:
                report["quality_assessment"] = "🔴 Плохой результат"
                report["insights_gained"].append(
                    f"Запрос требует доработки: низкая релевантность {avg_relevance:.0f}/100"
                )
            
            # Анализируем кластеры
            successful_clusters = [r[1] for r in results if r[4] and r[4] >= self.min_ai_relevance]
            if successful_clusters:
                most_common = max(set(successful_clusters), key=successful_clusters.count)
                report["insights_gained"].append(
                    f"Релевантный кластер: {most_common}"
                )
            
            # Анализируем технологии
            successful_techs = []
            for r in results:
                if r[4] and r[4] >= self.min_ai_relevance and r[2]:
                    successful_techs.append(r[2])
            
            if successful_techs:
                # Извлекаем ключевые технологии
                tech_words = []
                for tech_str in successful_techs[:3]:
                    if tech_str:
                        words = tech_str.split(';')[:2]  # Первые 2
                        tech_words.extend(words)
                
                if tech_words:
                    report["insights_gained"].append(
                        f"Релевантные технологии: {', '.join(tech_words[:3])}"
                    )
            
            conn.commit()
            conn.close()
            
            logger.info(f"📚 Инкрементальное обучение: query_id={query_id}, качество={report['quality_assessment']}")
            
        except Exception as e:
            logger.error(f"Ошибка инкрементального обучения: {e}")
            report["error"] = str(e)
        
        return report
    
    def _update_pattern_incremental(self, cursor, query_text: str, 
                                    results: List, avg_relevance: float):
        """
        Быстрое обновление паттерна (без глубокого анализа)
        """
        try:
            # Извлекаем ключевые слова (упрощенно)
            keywords = self._extract_keywords_fast(query_text)
            keywords_str = ", ".join(keywords[:5])
            
            # Определяем категорию (упрощенно)
            category = self._categorize_query_fast(query_text)
            
            # Получаем лучший кластер
            best_cluster = ""
            for r in results:
                if r[4] and r[4] >= self.min_ai_relevance and r[1]:
                    best_cluster = r[1]
                    break
            
            if not best_cluster:
                return
            
            # Проверяем существование паттерна
            cursor.execute("""
                SELECT id, usage_count, success_rate 
                FROM query_patterns
                WHERE query_type = ? AND keywords = ?
            """, (category, keywords_str))
            
            existing = cursor.fetchone()
            
            if existing:
                # Обновляем существующий (инкрементально)
                pattern_id, usage_count, old_success_rate = existing
                
                # Скользящее среднее
                new_success_rate = (old_success_rate * 0.9 + (avg_relevance / 100) * 0.1)
                
                cursor.execute("""
                    UPDATE query_patterns
                    SET usage_count = usage_count + 1,
                        success_rate = ?,
                        relevant_clusters = ?
                    WHERE id = ?
                """, (new_success_rate, best_cluster, pattern_id))
                
                logger.debug(f"Паттерн обновлен: {category} (usage={usage_count+1})")
            else:
                # Создаем новый паттерн
                cursor.execute("""
                    INSERT INTO query_patterns
                    (query_type, keywords, relevant_clusters, relevant_technologies,
                     example_query, example_startups, success_rate, usage_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    category,
                    keywords_str,
                    best_cluster,
                    "",  # Заполним при полном обучении
                    query_text[:200],
                    "",  # Заполним при полном обучении
                    avg_relevance / 100
                ))
                
                logger.info(f"✨ Новый паттерн создан: {category}")
                
        except Exception as e:
            logger.error(f"Ошибка обновления паттерна: {e}")
    
    def _extract_keywords_fast(self, text: str) -> List[str]:
        """Быстрое извлечение ключевых слов"""
        import re
        
        stop_words = {'в', 'на', 'с', 'для', 'из', 'и', 'или', 'до', 'по'}
        words = re.findall(r'\b[а-яёa-z]{4,}\b', text.lower())
        keywords = [w for w in words if w not in stop_words]
        
        return keywords[:5]
    
    def _categorize_query_fast(self, query_text: str) -> str:
        """Быстрая категоризация"""
        query_lower = query_text.lower()
        
        # Упрощенные категории
        if any(w in query_lower for w in ['ai', 'искусственный', 'нейро', 'машинное']):
            return 'ai_ml'
        elif any(w in query_lower for w in ['экология', 'переработка', 'устойчив', 'clean']):
            return 'clean_tech'
        elif any(w in query_lower for w in ['медицин', 'здравоохран', 'диагност']):
            return 'medtech'
        elif any(w in query_lower for w in ['финанс', 'банк', 'блокчейн', 'крипто']):
            return 'fintech'
        elif any(w in query_lower for w in ['энергет', 'электро', 'солнечн']):
            return 'energy'
        elif any(w in query_lower for w in ['робот', 'дрон', 'бпла', 'автоматиз']):
            return 'robotics'
        else:
            return 'general'
    
    def get_quick_stats(self) -> Dict:
        """Быстрая статистика для отладки"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Последние 5 запросов
            cursor.execute("""
                SELECT q.id, q.query_text, AVG(r.ai_relevance) as avg_rel
                FROM queries q
                JOIN query_results r ON q.id = r.query_id
                WHERE r.ai_relevance > 0
                GROUP BY q.id
                ORDER BY q.timestamp DESC
                LIMIT 5
            """)
            
            recent_queries = cursor.fetchall()
            conn.close()
            
            return {
                "recent_queries": [
                    {
                        "id": q[0],
                        "text": q[1][:50] + "...",
                        "avg_relevance": q[2]
                    }
                    for q in recent_queries
                ]
            }
        except Exception as e:
            logger.error(f"Ошибка статистики: {e}")
            return {}

