"""
RAG-сервис для семантического поиска стартапов
Использует GigaChat Embeddings для максимально точного семантического поиска
"""
import json
import numpy as np
from typing import List, Dict, Tuple
from gigachat import GigaChat
from config import GIGACHAT_API_TOKEN
from logger import logger

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("⚠️ scikit-learn не установлен, TF-IDF fallback недоступен")


class RAGService:
    def __init__(self):
        self.giga = None
        self.embeddings_cache = {}  # Кэш эмбеддингов
        self.startup_vectors = []  # Список (startup_id, vector)
        self.startup_texts = {}  # Словарь {startup_id: full_text}
        self.use_tfidf = False  # Флаг использования TF-IDF
        self.tfidf_vectorizer = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Инициализация GigaChat для embeddings"""
        try:
            # Инициализируем GigaChat для embeddings
            logger.info("💡 Используется GigaChat Embeddings (максимальная точность)")
            self.giga = GigaChat(
                credentials=GIGACHAT_API_TOKEN,
                scope="GIGACHAT_API_PERS",
                verify_ssl_certs=False,
                timeout=60  # Увеличен таймаут для embeddings
            )
            self.use_tfidf = False
            logger.info("✅ RAG Service: GigaChat Embeddings инициализирован")
            
            # TF-IDF как fallback
            if SKLEARN_AVAILABLE:
                self.tfidf_vectorizer = TfidfVectorizer(
                    max_features=1000,
                    ngram_range=(1, 2),
                    min_df=2,
                    max_df=0.8,
                    sublinear_tf=True
                )
                logger.info("✅ TF-IDF fallback готов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации GigaChat Embeddings: {e}")
            logger.info("💡 Переключаемся на TF-IDF fallback")
            self.giga = None
            self.use_tfidf = True
            
            if SKLEARN_AVAILABLE:
                self.tfidf_vectorizer = TfidfVectorizer(
                    max_features=1000,
                    ngram_range=(1, 2),
                    min_df=2,
                    max_df=0.8,
                    sublinear_tf=True
                )
                logger.info("✅ RAG Service: TF-IDF векторизация готова")
            else:
                logger.error("❌ Ни GigaChat Embeddings, ни TF-IDF недоступны")
    
    def _expand_query_with_gigachat(self, query: str) -> str:
        """
        Умное расширение запроса через GigaChat
        Вместо жестко прописанных синонимов, GigaChat сам понимает контекст
        
        Пример:
        - Запрос: "дроны" → "дрон беспилотник бпла квадрокоптер uav"
        - Запрос: "автомобили" → "автомобиль машина транспорт авто"
        - Запрос: "AI" → "искусственный интеллект нейросеть машинное обучение"
        """
        if not self.giga:
            return ""
        
        try:
            prompt = f"""Проанализируй запрос пользователя и извлеки ключевые концепции.
Для каждой концепции добавь синонимы, похожие термины и варианты написания.

ЗАПРОС: {query}

ЗАДАЧА:
1. Найди главные концепции (например: "дроны", "AI", "медицина")
2. Для каждой концепции добавь:
   - Синонимы на русском и английском
   - Технические термины
   - Аббревиатуры
   - Похожие концепции

ФОРМАТ ОТВЕТА (только ключевые слова через пробел, без объяснений):
[ключевое_слово1] [синоним1] [синоним2] [аббревиатура] [технический_термин] ...

ПРИМЕРЫ:
Запрос: "стартап с дронами"
Ответ: дрон дроны беспилотник беспилотный бпла бла uav квадрокоптер квадракоптер мультикоптер октокоптер коптер летательный

Запрос: "AI в медицине"
Ответ: искусственный интеллект ai нейросеть машинное обучение ml deep learning медицина здравоохранение диагностика лечение"""

            from gigachat.models import Chat, Messages, MessagesRole
            
            response = self.giga.chat(Chat(
                messages=[Messages(role=MessagesRole.USER, content=prompt)],
                temperature=0.3,
                max_tokens=150
            ))
            
            if response and response.choices:
                expanded = response.choices[0].message.content.strip().lower()
                logger.info(f"🤖 GigaChat расширил запрос: '{query}' → '{expanded[:100]}...'")
                return expanded
            
            return ""
            
        except Exception as e:
            logger.error(f"❌ Ошибка расширения запроса через GigaChat: {e}")
            return ""
    
    def _create_startup_text(self, startup: dict) -> str:
        """
        Создание полного текстового представления стартапа
        для векторизации
        """
        parts = []
        
        # Название и кластер (важно для поиска)
        if startup.get("name"):
            parts.append(f"Компания: {startup['name']}")
        if startup.get("cluster"):
            parts.append(f"Кластер: {startup['cluster']}")
        
        # Описания (основной контент)
        if startup.get("company_description"):
            parts.append(f"Описание: {startup['company_description'][:500]}")
        elif startup.get("description"):
            parts.append(f"Описание: {startup['description'][:500]}")
        
        if startup.get("product_description"):
            parts.append(f"Продукты: {startup['product_description'][:400]}")
        
        if startup.get("project_description"):
            parts.append(f"Описание проектов: {startup['project_description'][:400]}")
        
        # Технологии (критично для поиска)
        if startup.get("technologies"):
            parts.append(f"Технологии: {startup['technologies'][:300]}")
        
        if startup.get("product_names"):
            parts.append(f"Названия продуктов: {startup['product_names'][:200]}")
        
        if startup.get("project_names"):
            parts.append(f"Проекты: {startup['project_names'][:200]}")
        
        # Отрасли и категории
        if startup.get("industries"):
            parts.append(f"Отрасли: {startup['industries'][:200]}")
        
        if startup.get("category"):
            parts.append(f"Сферы: {startup['category']}")
        
        # IRL/CRL описания (содержат ценную информацию)
        if startup.get("irl_description"):
            parts.append(f"IRL: {startup['irl_description'][:150]}")
        
        if startup.get("crl_description"):
            parts.append(f"CRL: {startup['crl_description'][:150]}")
        
        return " ".join(parts)
    
    def get_embedding(self, text: str) -> np.ndarray:
        """Получение эмбеддинга для текста через GigaChat"""
        if not self.giga:
            return None
        
        # Проверяем кэш
        if text in self.embeddings_cache:
            return self.embeddings_cache[text]
        
        try:
            # Ограничиваем длину текста
            text = text[:2000]
            
            # Правильный вызов GigaChat Embeddings API
            response = self.giga.embeddings([text])
            
            # Обработка ответа
            if response and hasattr(response, 'data') and len(response.data) > 0:
                embedding_data = response.data[0]
                
                # Получаем вектор
                if hasattr(embedding_data, 'embedding'):
                    vector = np.array(embedding_data.embedding)
                elif isinstance(embedding_data, dict) and 'embedding' in embedding_data:
                    vector = np.array(embedding_data['embedding'])
                else:
                    vector = np.array(embedding_data)
                
                self.embeddings_cache[text] = vector
                return vector
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения эмбеддинга от GigaChat: {e}")
            logger.info("💡 Попытка использовать TF-IDF fallback")
            return None
    
    def index_startups(self, startups: List[dict], progress_callback=None):
        """
        Индексация стартапов - создание векторов для всех стартапов
        """
        logger.info(f"🔄 Начало индексации {len(startups)} стартапов...")
        
        self.startup_vectors = []
        self.startup_texts = {}
        
        # Собираем тексты
        texts = []
        startup_ids = []
        
        for startup in startups:
            startup_id = startup.get("id", "")
            if not startup_id:
                continue
            
            full_text = self._create_startup_text(startup)
            self.startup_texts[startup_id] = full_text
            texts.append(full_text)
            startup_ids.append(startup_id)
        
        # Векторизация
        if self.use_tfidf and self.tfidf_vectorizer:
            # TF-IDF векторизация (быстро, без API)
            logger.info("🔄 Используется TF-IDF векторизация...")
            try:
                vectors = self.tfidf_vectorizer.fit_transform(texts).toarray()
                self.startup_vectors = [(startup_ids[i], vectors[i]) for i in range(len(startup_ids))]
                logger.info(f"✅ TF-IDF: Индексировано {len(self.startup_vectors)} стартапов")
            except Exception as e:
                logger.error(f"Ошибка TF-IDF векторизации: {e}")
        else:
            # GigaChat Embeddings (медленно, но качественно)
            logger.info("🔄 Используется GigaChat Embeddings...")
            for i, (startup_id, text) in enumerate(zip(startup_ids, texts)):
                try:
                    vector = self.get_embedding(text)
                    if vector is not None:
                        self.startup_vectors.append((startup_id, vector))
                    
                    # Прогресс
                    if progress_callback and (i + 1) % 100 == 0:
                        progress_callback(i + 1, len(texts))
                    
                except Exception as e:
                    logger.error(f"Ошибка индексации стартапа: {e}")
        
        logger.info(f"✅ Индексировано {len(self.startup_vectors)} стартапов")
        return len(self.startup_vectors)
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Вычисление косинусного сходства"""
        try:
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)
        except:
            return 0.0
    
    def semantic_search(self, query: str, top_k: int = 50) -> List[Tuple[str, float]]:
        """
        Семантический поиск стартапов по запросу
        Возвращает список (startup_id, similarity_score)
        """
        if len(self.startup_vectors) == 0:
            logger.warning("RAG Service не готов к поиску")
            return []
        
        try:
            # Получаем вектор запроса
            if self.use_tfidf and self.tfidf_vectorizer:
                # TF-IDF векторизация запроса
                query_vector = self.tfidf_vectorizer.transform([query]).toarray()[0]
            else:
                # GigaChat Embeddings
                query_vector = self.get_embedding(query)
                if query_vector is None:
                    return []
            
            # Вычисляем сходство со всеми стартапами
            similarities = []
            for startup_id, startup_vector in self.startup_vectors:
                similarity = self.cosine_similarity(query_vector, startup_vector)
                similarities.append((startup_id, similarity))
            
            # Сортируем по убыванию сходства
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # Возвращаем топ-K
            top_results = similarities[:top_k]
            logger.info(f"🔍 RAG поиск: найдено {len(top_results)} релевантных стартапов (макс. сходство: {top_results[0][1]:.3f})")
            
            return top_results
            
        except Exception as e:
            logger.error(f"Ошибка семантического поиска: {e}")
            return []
    
    def hybrid_search(self, query: str, filters: dict, all_startups: List[dict], 
                     top_k: int = 50, filter_functions: dict = None) -> List[dict]:
        """
        Гибридный поиск: семантический + МЯГКИЕ фильтры
        
        НОВАЯ ЛОГИКА:
        1. Расширяем запрос через GigaChat (понимание контекста)
        2. Семантический поиск → топ-100 по similarity
        3. Добавляем similarity score ко всем
        4. Применяем ТОЛЬКО критичные фильтры (status, max_profit_limit, стартап)
        5. Сортируем по similarity
        6. Возвращаем топ-K, даже если фильтры не идеальны
        
        Цель: ВСЕГДА выводить результаты, отсортированные по relevance
        """
        # 1. Расширяем запрос для лучшего понимания контекста
        expanded_query = self._expand_query_with_gigachat(query)
        
        # Используем расширенный запрос для семантического поиска
        search_query = f"{query} {expanded_query}" if expanded_query else query
        logger.info(f"🔍 Поисковый запрос (расширенный): {search_query[:150]}...")
        
        # 2. Семантический поиск (берем больше для запаса перед фильтрацией)
        # top_k уже увеличен до 200, умножаем на 1.5 для запаса
        semantic_results = self.semantic_search(search_query, top_k=int(top_k * 1.5))
        
        if not semantic_results:
            logger.warning("Семантический поиск не дал результатов")
            return []
        
        # 2. Получаем стартапы по ID и добавляем similarity
        startup_ids = {startup_id for startup_id, _ in semantic_results}
        candidate_startups = [s for s in all_startups if s.get("id") in startup_ids]
        
        # Добавляем similarity score к каждому стартапу
        similarity_map = {startup_id: score for startup_id, score in semantic_results}
        for startup in candidate_startups:
            startup['rag_similarity'] = similarity_map.get(startup.get("id", ""), 0)
        
        logger.info(f"🔍 Семантический поиск: {len(candidate_startups)} кандидатов")
        
        # 3. Hard filters (critical only)
        filtered_startups = candidate_startups
        
        if filter_functions:
            max_profit_limit = filters.get("max_profit_limit")
            get_max_profit = filter_functions.get('get_max_profit')
            determine_stage = filter_functions.get('determine_stage')
            extract_level_value = filter_functions.get('extract_level_value')
            
            if max_profit_limit and get_max_profit:
                count_before = len(filtered_startups)
                filtered_startups = [s for s in filtered_startups if get_max_profit(s) <= max_profit_limit]
                logger.info(f"🔍 Фильтр 'max_profit_limit' (<= {max_profit_limit/1_000_000:.0f}M): {count_before} -> {len(filtered_startups)}")
            
            status_filter = filters.get("status", [])
            if status_filter and len(status_filter) > 0:
                count_before = len(filtered_startups)
                filtered_startups = [
                    s for s in filtered_startups
                    if s.get("status", "").lower() in [st.lower() for st in status_filter]
                ]
                logger.info(f"🔍 Фильтр 'status': {count_before} -> {len(filtered_startups)}")
            
            query_lower = query.lower()
            if "стартап" in query_lower and determine_stage:
                count_before = len(filtered_startups)
                filtered_startups = [
                    s for s in filtered_startups 
                    if determine_stage(s) in ["Pre-seed", "Seed", "Round A"]
                ]
                logger.info(f"🎯 Фильтр 'стартап': {count_before} -> {len(filtered_startups)}")
        
            # 4. Soft-filter scoring: boost/penalize by structural match
            stage_filter = filters.get("stage", [])
            cluster_filter = filters.get("cluster", [])
            trl_filter = filters.get("trl", [])
            irl_filter = filters.get("irl", [])

            has_soft = bool(stage_filter or cluster_filter or trl_filter or irl_filter)
            if has_soft:
                for s in filtered_startups:
                    bonus = 0.0
                    if stage_filter and determine_stage:
                        if determine_stage(s) in stage_filter:
                            bonus += 0.12
                        else:
                            bonus -= 0.08
                    if cluster_filter:
                        sc = s.get("cluster", "").lower()
                        if any(c.lower() in sc for c in cluster_filter):
                            bonus += 0.08
                        else:
                            bonus -= 0.04
                    if trl_filter and extract_level_value:
                        trl_val = extract_level_value(s.get("trl", ""))
                        if trl_val in trl_filter or trl_val >= (min(trl_filter) if trl_filter else 0):
                            bonus += 0.06
                    if irl_filter and extract_level_value:
                        irl_val = extract_level_value(s.get("irl", ""))
                        if irl_val in irl_filter or irl_val >= (min(irl_filter) if irl_filter else 0):
                            bonus += 0.04
                    s["rag_similarity"] = max(0, s.get("rag_similarity", 0) + bonus)
                logger.info(f"🎯 Soft-filter scoring: stage={stage_filter}, cluster={cluster_filter}, trl={trl_filter}")
        
        # 5. Sort by adjusted similarity
        filtered_startups.sort(
            key=lambda s: s.get('rag_similarity', 0),
            reverse=True
        )
        
        logger.info(f"✅ После фильтрации + soft-scoring: {len(filtered_startups)} стартапов")
        
        return filtered_startups[:top_k]
    
    def save_index(self, filepath: str = "rag_index.json"):
        """Сохранение индекса в файл"""
        try:
            data = {
                "vectors": [(sid, vec.tolist()) for sid, vec in self.startup_vectors],
                "texts": self.startup_texts
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            logger.info(f"✅ Индекс сохранен в {filepath}")
        except Exception as e:
            logger.error(f"Ошибка сохранения индекса: {e}")
    
    def load_index(self, filepath: str = "rag_index.json") -> bool:
        """Загрузка индекса из файла"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.startup_vectors = [(sid, np.array(vec)) for sid, vec in data["vectors"]]
            self.startup_texts = data["texts"]
            
            logger.info(f"✅ Индекс загружен из {filepath}: {len(self.startup_vectors)} стартапов")
            return True
        except FileNotFoundError:
            logger.warning(f"Файл индекса {filepath} не найден")
            return False
        except Exception as e:
            logger.error(f"Ошибка загрузки индекса: {e}")
            return False

