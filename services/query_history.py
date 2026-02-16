"""
Модуль для хранения и анализа истории запросов
Используется для адаптивных промптов и улучшения точности
"""
import sqlite3
import logging
from typing import List, Dict, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class QueryHistory:
    """
    Хранение истории запросов для адаптивного обучения
    
    Структура БД:
    - queries: запросы пользователей
    - query_results: результаты поиска (стартапы)
    - query_patterns: паттерны успешных запросов
    """
    
    def __init__(self, db_path: str = "query_history.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализация БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Таблица запросов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    query_text TEXT NOT NULL,
                    model_type TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expanded_query TEXT,
                    filters_used TEXT
                )
            """)
            
            # Таблица результатов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS query_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id INTEGER,
                    startup_name TEXT,
                    startup_id TEXT,
                    rag_similarity REAL,
                    ai_relevance REAL,
                    position INTEGER,
                    cluster TEXT,
                    technologies TEXT,
                    FOREIGN KEY (query_id) REFERENCES queries(id)
                )
            """)
            
            # Таблица паттернов (для few-shot learning)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS query_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_type TEXT,
                    keywords TEXT,
                    relevant_clusters TEXT,
                    relevant_technologies TEXT,
                    example_query TEXT,
                    example_startups TEXT,
                    success_rate REAL DEFAULT 0.0,
                    usage_count INTEGER DEFAULT 0
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info("✅ БД истории запросов инициализирована")
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")
    
    def save_query(self, user_id: int, query_text: str, model_type: str, 
                   expanded_query: str = "", filters_used: Dict = None) -> int:
        """
        Сохранение запроса
        
        Returns:
            query_id для связи с результатами
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO queries (user_id, query_text, model_type, expanded_query, filters_used)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, query_text, model_type, expanded_query, json.dumps(filters_used or {})))
            
            query_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            logger.info(f"💾 Запрос сохранен: ID={query_id}")
            return query_id
        except Exception as e:
            logger.error(f"Ошибка сохранения запроса: {e}")
            return -1
    
    def save_results(self, query_id: int, results: List[Dict]):
        """Сохранение результатов поиска"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for i, startup in enumerate(results):
                cursor.execute("""
                    INSERT INTO query_results 
                    (query_id, startup_name, startup_id, rag_similarity, ai_relevance, 
                     position, cluster, technologies)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    query_id,
                    startup.get('name', 'N/A'),
                    startup.get('id', ''),
                    startup.get('rag_similarity', 0),
                    startup.get('ai_relevance', 0),
                    i + 1,
                    startup.get('cluster', ''),
                    startup.get('technologies', '')[:200]
                ))
            
            conn.commit()
            conn.close()
            logger.info(f"💾 Сохранено {len(results)} результатов для query_id={query_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения результатов: {e}")
    
    def get_similar_queries(self, query_text: str, limit: int = 3) -> List[Dict]:
        """
        Поиск похожих запросов из истории
        
        Returns:
            Список похожих запросов с их результатами
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Простой поиск по ключевым словам (можно улучшить через embeddings)
            keywords = query_text.lower().split()[:5]  # Берем первые 5 слов
            
            similar_queries = []
            for keyword in keywords:
                cursor.execute("""
                    SELECT q.id, q.query_text, q.expanded_query,
                           GROUP_CONCAT(r.startup_name, ', ') as relevant_startups,
                           GROUP_CONCAT(r.cluster, ', ') as clusters
                    FROM queries q
                    LEFT JOIN query_results r ON q.id = r.query_id AND r.ai_relevance > 70
                    WHERE LOWER(q.query_text) LIKE ?
                    GROUP BY q.id
                    ORDER BY q.timestamp DESC
                    LIMIT ?
                """, (f'%{keyword}%', limit))
                
                rows = cursor.fetchall()
                for row in rows:
                    similar_queries.append({
                        'query_id': row[0],
                        'query_text': row[1],
                        'expanded_query': row[2],
                        'relevant_startups': row[3] or '',
                        'clusters': row[4] or ''
                    })
                
                if len(similar_queries) >= limit:
                    break
            
            conn.close()
            return similar_queries[:limit]
        except Exception as e:
            logger.error(f"Ошибка поиска похожих запросов: {e}")
            return []
    
    def get_query_patterns(self, query_text: str) -> List[Dict]:
        """
        Получение паттернов для few-shot learning
        
        Returns:
            Список релевантных паттернов с примерами
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Извлекаем ключевые слова
            keywords = query_text.lower().split()[:5]
            
            patterns = []
            for keyword in keywords:
                cursor.execute("""
                    SELECT query_type, keywords, relevant_clusters, 
                           relevant_technologies, example_query, example_startups,
                           success_rate
                    FROM query_patterns
                    WHERE keywords LIKE ? OR query_type LIKE ?
                    ORDER BY success_rate DESC, usage_count DESC
                    LIMIT 3
                """, (f'%{keyword}%', f'%{keyword}%'))
                
                rows = cursor.fetchall()
                for row in rows:
                    patterns.append({
                        'query_type': row[0],
                        'keywords': row[1],
                        'relevant_clusters': row[2],
                        'relevant_technologies': row[3],
                        'example_query': row[4],
                        'example_startups': row[5],
                        'success_rate': row[6]
                    })
            
            conn.close()
            return patterns[:3]  # Топ-3 паттерна
        except Exception as e:
            logger.error(f"Ошибка получения паттернов: {e}")
            return []
    
    def update_pattern(self, query_type: str, keywords: str, relevant_clusters: str,
                      relevant_technologies: str, example_query: str, example_startups: str):
        """Обновление/создание паттерна для few-shot learning"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Проверяем, существует ли паттерн
            cursor.execute("""
                SELECT id, usage_count FROM query_patterns
                WHERE query_type = ? AND keywords = ?
            """, (query_type, keywords))
            
            row = cursor.fetchone()
            if row:
                # Обновляем существующий
                cursor.execute("""
                    UPDATE query_patterns
                    SET relevant_clusters = ?, relevant_technologies = ?,
                        example_query = ?, example_startups = ?,
                        usage_count = usage_count + 1
                    WHERE id = ?
                """, (relevant_clusters, relevant_technologies, example_query, 
                      example_startups, row[0]))
            else:
                # Создаем новый
                cursor.execute("""
                    INSERT INTO query_patterns 
                    (query_type, keywords, relevant_clusters, relevant_technologies,
                     example_query, example_startups, usage_count)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, (query_type, keywords, relevant_clusters, relevant_technologies,
                      example_query, example_startups))
            
            conn.commit()
            conn.close()
            logger.info(f"💾 Паттерн обновлен: {query_type}")
        except Exception as e:
            logger.error(f"Ошибка обновления паттерна: {e}")
    
    def get_statistics(self) -> Dict:
        """Статистика для анализа"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute("SELECT COUNT(*) FROM queries")
            total_queries = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM query_results")
            total_results = cursor.fetchone()[0]
            
            cursor.execute("SELECT AVG(ai_relevance) FROM query_results WHERE ai_relevance > 0")
            avg_relevance = cursor.fetchone()[0] or 0
            
            # Топ кластеры
            cursor.execute("""
                SELECT cluster, COUNT(*) as cnt
                FROM query_results
                WHERE cluster != ''
                GROUP BY cluster
                ORDER BY cnt DESC
                LIMIT 5
            """)
            top_clusters = cursor.fetchall()
            
            conn.close()
            
            return {
                'total_queries': total_queries,
                'total_results': total_results,
                'avg_relevance': round(avg_relevance, 2),
                'top_clusters': [{'cluster': c[0], 'count': c[1]} for c in top_clusters]
            }
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}

