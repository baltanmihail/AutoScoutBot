"""
Модуль самообучения для AutoScoutBot
Автоматически улучшает систему на основе накопленных данных
"""
import logging
import sqlite3
from typing import List, Dict, Tuple
import json
from collections import defaultdict
import re

logger = logging.getLogger(__name__)

class SelfLearningEngine:
    """
    Движок самообучения
    
    Что делает:
    1. Анализирует успешные запросы (AI relevance > 80)
    2. Выявляет паттерны (какие слова → какие кластеры/технологии)
    3. Автоматически создает/обновляет few-shot примеры
    4. Генерирует синонимы для расширения запросов
    5. Экспортирует данные для fine-tuning
    """
    
    def __init__(self, db_path: str = "query_history.db", min_samples: int = None):
        self.db_path = db_path
        
        # Загружаем настройки из config.py
        try:
            from config import SELF_LEARNING, FINE_TUNING
            self.min_samples = min_samples or SELF_LEARNING.get('min_samples', 5)
            self.min_ai_relevance = SELF_LEARNING.get('min_ai_relevance', 80)
            self.max_patterns = SELF_LEARNING.get('max_patterns', 50)
            self.max_few_shot = SELF_LEARNING.get('max_few_shot_examples', 10)
            self.fine_tuning_min = FINE_TUNING.get('min_examples', 100)
            self.fine_tuning_output = FINE_TUNING.get('output_file', 'finetuning_dataset.jsonl')
        except ImportError:
            self.min_samples = min_samples or 5
            self.min_ai_relevance = 80
            self.max_patterns = 50
            self.max_few_shot = 10
            self.fine_tuning_min = 100
            self.fine_tuning_output = 'finetuning_dataset.jsonl'
        
    def analyze_and_learn(self) -> Dict:
        """
        Главная функция: анализирует данные и обучается
        
        Returns:
            Отчет о проделанной работе
        """
        logger.info("🧠 Запуск самообучения...")
        
        report = {
            "patterns_discovered": 0,
            "patterns_updated": 0,
            "synonyms_generated": 0,
            "few_shot_created": 0,
            "recommendations": []
        }
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 1. Проверяем, достаточно ли данных
            cursor.execute("SELECT COUNT(*) FROM queries")
            total_queries = cursor.fetchone()[0]
            
            if total_queries < self.min_samples:
                logger.info(f"⏳ Недостаточно данных: {total_queries}/{self.min_samples}")
                report["recommendations"].append(
                    f"Накопите минимум {self.min_samples} запросов для обучения"
                )
                conn.close()
                return report
            
            # 2. Выявляем паттерны из успешных запросов
            patterns = self._discover_patterns(cursor)
            report["patterns_discovered"] = len(patterns)
            
            # 3. Обновляем/создаем паттерны в БД
            for pattern in patterns:
                if self._update_or_create_pattern(cursor, pattern):
                    report["patterns_updated"] += 1
            
            # 4. Генерируем синонимы
            synonyms = self._generate_synonyms(cursor)
            report["synonyms_generated"] = len(synonyms)
            
            # 5. Создаем новые few-shot примеры
            few_shot_examples = self._create_few_shot_examples(cursor, patterns)
            report["few_shot_created"] = len(few_shot_examples)
            
            # Сохраняем few-shot примеры
            if few_shot_examples:
                self._save_few_shot_examples(few_shot_examples)
            
            conn.commit()
            conn.close()
            
            # 6. Рекомендации
            report["recommendations"] = self._generate_recommendations(
                total_queries, patterns, synonyms
            )
            
            logger.info(f"✅ Самообучение завершено: "
                       f"{report['patterns_discovered']} паттернов, "
                       f"{report['few_shot_created']} примеров")
            
        except Exception as e:
            logger.error(f"❌ Ошибка самообучения: {e}")
            report["error"] = str(e)
        
        return report
    
    def _discover_patterns(self, cursor) -> List[Dict]:
        """Выявление паттернов из успешных запросов"""
        
        # Находим успешные запросы (AI relevance > min_ai_relevance)
        cursor.execute("""
            SELECT 
                q.query_text,
                r.cluster,
                r.technologies,
                r.ai_relevance,
                COUNT(*) as frequency
            FROM queries q
            JOIN query_results r ON q.id = r.query_id
            WHERE r.ai_relevance >= ?
            GROUP BY q.query_text, r.cluster
            HAVING COUNT(*) >= ?
            ORDER BY frequency DESC, r.ai_relevance DESC
        """, (self.min_ai_relevance, self.min_samples))
        
        rows = cursor.fetchall()
        
        patterns = []
        for query_text, cluster, technologies, ai_relevance, frequency in rows:
            # Извлекаем ключевые слова
            keywords = self._extract_keywords(query_text)
            
            pattern = {
                "query_type": self._categorize_query(query_text),
                "keywords": ", ".join(keywords[:10]),
                "relevant_clusters": cluster,
                "relevant_technologies": technologies or "",
                "example_query": query_text,
                "success_rate": ai_relevance / 100,
                "frequency": frequency
            }
            
            patterns.append(pattern)
        
        logger.info(f"🔍 Выявлено {len(patterns)} паттернов")
        return patterns
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Извлечение ключевых слов из текста"""
        # Удаляем стоп-слова
        stop_words = {
            'в', 'на', 'с', 'для', 'из', 'и', 'или', 'также', 'более', 'менее',
            'до', 'после', 'стартап', 'компания', 'проект', 'область', 'сфера'
        }
        
        # Токенизация
        words = re.findall(r'\b[а-яёa-z]+\b', text.lower())
        
        # Фильтрация
        keywords = [w for w in words if w not in stop_words and len(w) > 3]
        
        # Подсчет частоты
        from collections import Counter
        word_freq = Counter(keywords)
        
        return [word for word, _ in word_freq.most_common(10)]
    
    def _categorize_query(self, query_text: str) -> str:
        """Категоризация запроса"""
        query_lower = query_text.lower()
        
        categories = {
            "ai_ml": ["ai", "искусственный интеллект", "машинное обучение", "нейросети", "ml"],
            "clean_tech": ["экология", "переработка", "устойчивое развитие", "clean tech", "зеленые"],
            "medtech": ["медицина", "здравоохранение", "диагностика", "телемедицина"],
            "fintech": ["финансы", "банк", "блокчейн", "криптовалюта", "платежи"],
            "energy": ["энергетика", "электро", "солнечн", "водород"],
            "agro": ["сельское хозяйство", "агро", "фермер", "растени"],
            "robotics": ["робот", "автоматизация", "дрон", "бпла", "беспилотн"],
        }
        
        for category, keywords in categories.items():
            if any(kw in query_lower for kw in keywords):
                return category
        
        return "general"
    
    def _update_or_create_pattern(self, cursor, pattern: Dict) -> bool:
        """Обновление или создание паттерна в БД"""
        try:
            # Проверяем существование
            cursor.execute("""
                SELECT id, usage_count, success_rate FROM query_patterns
                WHERE query_type = ? AND keywords = ?
            """, (pattern["query_type"], pattern["keywords"]))
            
            existing = cursor.fetchone()
            
            if existing:
                pattern_id, usage_count, old_success_rate = existing
                
                # Обновляем (скользящее среднее для success_rate)
                new_success_rate = (old_success_rate + pattern["success_rate"]) / 2
                
                cursor.execute("""
                    UPDATE query_patterns
                    SET relevant_clusters = ?,
                        relevant_technologies = ?,
                        example_query = ?,
                        success_rate = ?,
                        usage_count = usage_count + ?
                    WHERE id = ?
                """, (
                    pattern["relevant_clusters"],
                    pattern["relevant_technologies"],
                    pattern["example_query"],
                    new_success_rate,
                    pattern["frequency"],
                    pattern_id
                ))
                
                logger.info(f"📝 Обновлен паттерн: {pattern['query_type']}")
            else:
                # Создаем новый
                cursor.execute("""
                    INSERT INTO query_patterns
                    (query_type, keywords, relevant_clusters, relevant_technologies,
                     example_query, example_startups, success_rate, usage_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pattern["query_type"],
                    pattern["keywords"],
                    pattern["relevant_clusters"],
                    pattern["relevant_technologies"],
                    pattern["example_query"],
                    "",  # example_startups заполним позже
                    pattern["success_rate"],
                    pattern["frequency"]
                ))
                
                logger.info(f"✨ Создан новый паттерн: {pattern['query_type']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления паттерна: {e}")
            return False
    
    def _generate_synonyms(self, cursor) -> Dict[str, List[str]]:
        """Генерация синонимов на основе успешных запросов"""
        
        # Находим запросы с похожими результатами
        cursor.execute("""
            SELECT DISTINCT
                q1.query_text,
                q2.query_text,
                r1.cluster,
                AVG(r1.ai_relevance) as avg_relevance
            FROM queries q1
            JOIN query_results r1 ON q1.id = r1.query_id
            JOIN query_results r2 ON r1.startup_name = r2.startup_name
            JOIN queries q2 ON r2.query_id = q2.id
            WHERE q1.id != q2.id
              AND r1.ai_relevance >= 70
              AND r2.ai_relevance >= 70
            GROUP BY q1.query_text, q2.query_text, r1.cluster
            HAVING COUNT(*) >= 2
        """)
        
        rows = cursor.fetchall()
        
        synonyms = defaultdict(set)
        for query1, query2, cluster, avg_rel in rows:
            # Извлекаем ключевые слова
            keywords1 = set(self._extract_keywords(query1))
            keywords2 = set(self._extract_keywords(query2))
            
            # Находим уникальные слова
            unique1 = keywords1 - keywords2
            unique2 = keywords2 - keywords1
            
            # Добавляем как синонимы
            for word1 in unique1:
                for word2 in unique2:
                    synonyms[word1].add(word2)
                    synonyms[word2].add(word1)
        
        # Конвертируем в обычный dict
        synonyms_dict = {k: list(v) for k, v in synonyms.items() if len(v) > 0}
        
        logger.info(f"🔤 Сгенерировано синонимов: {len(synonyms_dict)}")
        return synonyms_dict
    
    def _create_few_shot_examples(self, cursor, patterns: List[Dict]) -> List[Dict]:
        """Создание few-shot примеров из паттернов"""
        
        examples = []
        
        for pattern in patterns[:10]:  # Топ-10 паттернов
            # Находим лучшие и худшие результаты для этого паттерна
            cursor.execute("""
                SELECT r.startup_name, r.ai_relevance, r.cluster, r.technologies
                FROM queries q
                JOIN query_results r ON q.id = r.query_id
                WHERE q.query_text = ?
                ORDER BY r.ai_relevance DESC
                LIMIT 5
            """, (pattern["example_query"],))
            
            relevant = cursor.fetchall()
            
            if len(relevant) < 2:
                continue
            
            # Формируем пример
            example = {
                "category": pattern["query_type"],
                "query": pattern["example_query"],
                "relevant": [
                    f"{name} ({cluster})"
                    for name, rel, cluster, _ in relevant if rel >= 80
                ],
                "clusters": list(set([r[2] for r in relevant if r[1] >= 80])),
                "keywords": pattern["keywords"].split(", ")
            }
            
            examples.append(example)
        
        logger.info(f"📚 Создано few-shot примеров: {len(examples)}")
        return examples
    
    def _save_few_shot_examples(self, examples: List[Dict]):
        """Сохранение few-shot примеров в файл"""
        try:
            output_file = "ai_learning/learned_examples.py"
            
            content = '''"""
Автоматически сгенерированные few-shot примеры
Создано системой самообучения
"""

LEARNED_EXAMPLES = {
'''
            
            # Группируем по категориям
            by_category = defaultdict(list)
            for ex in examples:
                by_category[ex["category"]].append(ex)
            
            for category, category_examples in by_category.items():
                content += f'    "{category}": {{\n'
                content += f'        "description": "Автоматически выявленная категория",\n'
                content += f'        "examples": [\n'
                
                for ex in category_examples:
                    content += '            {\n'
                    content += f'                "query": "{ex["query"]}",\n'
                    content += f'                "relevant": {json.dumps(ex["relevant"], ensure_ascii=False)},\n'
                    content += f'                "clusters": {json.dumps(ex["clusters"], ensure_ascii=False)},\n'
                    content += f'                "keywords": {json.dumps(ex["keywords"], ensure_ascii=False)}\n'
                    content += '            },\n'
                
                content += '        ]\n'
                content += '    },\n'
            
            content += '}\n'
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"💾 Few-shot примеры сохранены: {output_file}")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения few-shot: {e}")
    
    def _generate_recommendations(self, total_queries: int, 
                                  patterns: List[Dict], 
                                  synonyms: Dict) -> List[str]:
        """Генерация рекомендаций по улучшению"""
        
        recommendations = []
        
        # Анализ количества данных
        if total_queries < 50:
            recommendations.append(
                f"📊 Накопите больше данных: {total_queries}/50 запросов. "
                f"Для качественного обучения нужно минимум 50."
            )
        elif total_queries < 200:
            recommendations.append(
                f"📊 Хороший прогресс: {total_queries}/200 запросов. "
                f"При 200+ система достигнет максимальной эффективности."
            )
        else:
            recommendations.append(
                f"✅ Отличный объем данных: {total_queries} запросов. "
                f"Система обучена хорошо!"
            )
        
        # Анализ паттернов
        if len(patterns) < 5:
            recommendations.append(
                f"🔍 Выявлено мало паттернов ({len(patterns)}). "
                f"Делайте более разнообразные запросы."
            )
        else:
            recommendations.append(
                f"✅ Выявлено {len(patterns)} паттернов. Система учится эффективно!"
            )
        
        # Анализ синонимов
        if len(synonyms) < 10:
            recommendations.append(
                f"🔤 Мало синонимов ({len(synonyms)}). "
                f"Попробуйте разные формулировки запросов."
            )
        
        # Рекомендация по fine-tuning
        if total_queries >= 100:
            recommendations.append(
                "🚀 Достаточно данных для fine-tuning! "
                "Запустите: python ai_learning/train_model.py"
            )
        
        return recommendations
    
    def export_for_finetuning(self, output_file: str = None) -> int:
        """
        Экспорт данных для fine-tuning GigaChat
        
        Формат JSONL (JSON Lines):
        {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
        """
        try:
            if output_file is None:
                output_file = self.fine_tuning_output
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Экспортируем только качественные примеры (AI relevance >= min_ai_relevance - 10)
            cursor.execute("""
                SELECT 
                    q.query_text,
                    r.startup_name,
                    r.cluster,
                    r.technologies,
                    r.ai_relevance,
                    r.rag_similarity
                FROM queries q
                JOIN query_results r ON q.id = r.query_id
                WHERE r.ai_relevance >= ?
                ORDER BY r.ai_relevance DESC
            """, (max(70, self.min_ai_relevance - 10),))
            
            rows = cursor.fetchall()
            conn.close()
            
            if len(rows) < self.fine_tuning_min:
                logger.warning(f"⚠️ Недостаточно данных для fine-tuning: {len(rows)}/{self.fine_tuning_min}")
                return 0
            
            # Формируем датасет
            with open(output_file, 'w', encoding='utf-8') as f:
                for query, startup, cluster, tech, ai_rel, rag_sim in rows:
                    # Формируем пример для fine-tuning
                    example = {
                        "messages": [
                            {
                                "role": "user",
                                "content": f"""Оцени релевантность стартапа запросу от 0 до 100.

Запрос: {query}

Стартап:
Название: {startup}
Кластер: {cluster}
Технологии: {tech or 'не указано'}

Ответ (только число от 0 до 100):"""
                            },
                            {
                                "role": "assistant",
                                "content": str(int(ai_rel))
                            }
                        ]
                    }
                    
                    f.write(json.dumps(example, ensure_ascii=False) + '\n')
            
            logger.info(f"✅ Экспортировано {len(rows)} примеров для fine-tuning: {output_file}")
            return len(rows)
            
        except Exception as e:
            logger.error(f"❌ Ошибка экспорта для fine-tuning: {e}")
            return 0

