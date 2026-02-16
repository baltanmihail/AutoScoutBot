"""
Утилиты для поиска стартапов
"""
import random
from logger import logger
from utils.startup_utils import (
    analyze_startup, determine_stage, extract_level_value, get_max_profit
)


def get_unique_startups(
    count: int,
    filters: dict,
    user_request: str = "",
    user_id: int = None,
    SKOLKOVO_DB=None,
    shown_startups=None,
    rag_service=None,
    query_history=None,
    continuous_learner=None,
    incremental_learner=None,
    RAG_ENABLED=False,
    RAG_TOP_K=200
):
    """
    Получить уникальные стартапы с применением фильтров и RAG-поиска
    
    Args:
        count: Количество стартапов для возврата
        filters: Словарь фильтров
        user_request: Текстовый запрос пользователя
        user_id: ID пользователя
        SKOLKOVO_DB: База данных стартапов
        shown_startups: Множество уже показанных стартапов
        rag_service: Сервис RAG-поиска
        query_history: История запросов
        continuous_learner: Объект для непрерывного обучения
        incremental_learner: Объект для инкрементального обучения
        RAG_ENABLED: Включен ли RAG
        RAG_TOP_K: Количество кандидатов для RAG-поиска
    
    Returns:
        Список выбранных стартапов
    """
    if SKOLKOVO_DB is None:
        return []
    
    if shown_startups is None:
        shown_startups = set()

    # Используем RAG если доступен и есть запрос пользователя
    if RAG_ENABLED and rag_service and user_request and len(rag_service.startup_vectors) > 0:
        logger.info("🔍 Используется RAG-поиск с улучшениями (Re-ranking + Few-shot)")
        
        # Гибридный поиск: семантический + фильтры
        filter_functions = {
            'extract_level_value': extract_level_value,
            'get_max_profit': get_max_profit,
            'determine_stage': determine_stage,
            'analyze_startup': analyze_startup
        }
        
        # Шаг 1: RAG поиск (быстрый, но неточный)
        filtered = rag_service.hybrid_search(
            query=user_request,
            filters=filters,
            all_startups=SKOLKOVO_DB,
            top_k=RAG_TOP_K,
            filter_functions=filter_functions
        )
        
        # Исключаем уже показанные
        available = [s for s in filtered if s.get("id", "") not in shown_startups]
        if len(available) < count:
            shown_startups.clear()
            available = filtered
        
        # Шаг 2: Re-ranking через GigaChat (медленный, но точный)
        # Берем топ-30 кандидатов для переоценки
        num_candidates = min(30, len(available))
        top_candidates = available[:num_candidates]
        
        if len(top_candidates) >= count and rag_service.giga:
            try:
                from services.reranker import ReRanker
                reranker = ReRanker(rag_service.giga)
                # Переранжируем топ-30, выбираем топ-10 для рандомизации
                reranked = reranker.rerank(user_request, top_candidates, top_k=min(10, len(top_candidates)))
                top_candidates = reranked
                logger.info(f"✅ Re-ranking: топ-{len(reranked)} переоценены через GigaChat")
            except Exception as e:
                logger.warning(f"⚠️ Re-ranking недоступен: {e}, используем RAG similarity")
        
        # Шаг 3: Рандомизация из топ-кандидатов
        if len(top_candidates) > count:
            # Взвешенный случайный выбор по AI relevance (если есть) или RAG similarity
            weights = [s.get('ai_relevance', s.get('rag_similarity', 0.5) * 100) for s in top_candidates]
            selected = random.choices(top_candidates, weights=weights, k=count)
            # Убираем дубликаты
            seen_ids = set()
            unique_selected = []
            for s in selected:
                if s.get("id") not in seen_ids:
                    unique_selected.append(s)
                    seen_ids.add(s.get("id"))
            selected = unique_selected[:count]
            # Сортируем по AI relevance или RAG similarity
            selected.sort(key=lambda s: s.get('ai_relevance', s.get('rag_similarity', 0) * 100), reverse=True)
        else:
            selected = top_candidates[:count]
        
        for s in selected:
            shown_startups.add(s.get("id", ""))
        
        # Шаг 4: Сохраняем в историю для адаптивного обучения
        if query_history and user_id:
            try:
                query_id = query_history.save_query(
                    user_id=user_id,
                    query_text=user_request,
                    model_type=filters.get('model_type', 'standard'),
                    expanded_query=getattr(rag_service, 'last_expanded_query', ''),
                    filters_used=filters
                )
                if query_id > 0:
                    query_history.save_results(query_id, selected)
                    logger.info(f"💾 Запрос сохранен в историю: ID={query_id}")
                    
                    # ИНКРЕМЕНТАЛЬНОЕ ОБУЧЕНИЕ (после каждого запроса)
                    try:
                        from config import CONTINUOUS_LEARNING
                        if CONTINUOUS_LEARNING.get('light_learning', True) and incremental_learner:
                            report = incremental_learner.learn_from_query(query_id)
                            if report.get('patterns_updated', 0) > 0:
                                logger.info(f"📚 Инкрементальное обучение: {report['quality_assessment']}")
                                for insight in report.get('insights_gained', [])[:2]:
                                    logger.info(f"   💡 {insight}")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка инкрементального обучения: {e}")
                    
                    # Уведомляем continuous learner о новом запросе (для глубокого обучения)
                    if continuous_learner:
                        continuous_learner.notify_new_query()
            except Exception as e:
                logger.warning(f"⚠️ Ошибка сохранения в историю: {e}")
        
        logger.info(f"✅ Итого: выбрано {len(selected)} стартапов из {len(top_candidates)} топ-кандидатов")
        return selected
    
    # Обычный поиск (fallback)
    logger.info("🔍 Используется обычный поиск")
    filtered = [s for s in SKOLKOVO_DB if s.get("website", "").strip() != ""]
    logger.info(f"🔍 Начальное количество стартапов с сайтом: {len(filtered)}")
    logger.info(f"🔍 Применяемые фильтры: {filters}")

    for key, value in filters.items():
        if isinstance(value, list) and len(value) <= 0:
            continue
        
        count_before = len(filtered)

        if key == "DeepTech":
            # Пропускаем, если значение пустое или невалидное
            if value and str(value).strip() and str(value).strip().isdigit():
                filtered = [s for s in filtered if analyze_startup(s)["DeepTech"] >= int(value)]
        elif key == "GenAI":
            if value and str(value).strip() in ["есть", "нет"]:
                filtered = [s for s in filtered if analyze_startup(s)["GenAI"] == value]
        elif key == "WOW":
            if value and str(value).strip() in ["да", "нет"]:
                filtered = [s for s in filtered if analyze_startup(s)["WOW"] == value]
        elif key == "category":
            if isinstance(value, list) and len(value) > 0:
                # Фильтруем по категориям с поиском по ключевым словам
                # Ищем в: category, cluster, company_description, description
                filtered = [
                    s for s in filtered
                    if any(
                        # Поиск в категориях (Сферы деятельности)
                        any(sel.strip().lower() in cat.strip().lower() or cat.strip().lower() in sel.strip().lower() 
                            for cat in str(s.get("category", "")).split(";"))
                        or
                        # Поиск в кластере
                        sel.strip().lower() in str(s.get("cluster", "")).lower()
                        or
                        # Поиск ключевых слов в описаниях
                        sel.strip().lower() in str(s.get("company_description", "")).lower()
                        or
                        sel.strip().lower() in str(s.get("description", "")).lower()
                        for sel in value
                    )
                ]
            elif not isinstance(value, list) and value and str(value).strip():
                # Частичное совпадение для одиночного значения с поиском в описаниях
                val_lower = value.strip().lower()
                filtered = [
                    s for s in filtered
                    if (
                        any(val_lower in cat.strip().lower() or cat.strip().lower() in val_lower 
                            for cat in str(s.get("category", "")).split(";"))
                        or val_lower in str(s.get("cluster", "")).lower()
                        or val_lower in str(s.get("company_description", "")).lower()
                        or val_lower in str(s.get("description", "")).lower()
                    )
                ]
        
        # ДОПОЛНИТЕЛЬНЫЙ ПОИСК ПО КЛЮЧЕВЫМ СЛОВАМ если category пустая
        # Это позволит находить компании по любым ключевым словам из запроса
        elif key == "keyword_search":
            if value and str(value).strip():
                keywords = str(value).strip().lower().split()
                # Ищем хотя бы одно ключевое слово во ВСЕХ текстовых полях
                filtered = [
                    s for s in filtered
                    if any(
                        keyword in str(s.get("company_description", "")).lower()
                        or keyword in str(s.get("description", "")).lower()
                        or keyword in str(s.get("product_description", "")).lower()
                        or keyword in str(s.get("category", "")).lower()
                        or keyword in str(s.get("cluster", "")).lower()
                        or keyword in str(s.get("technologies", "")).lower()
                        or keyword in str(s.get("product_names", "")).lower()
                        or keyword in str(s.get("project_names", "")).lower()
                        or keyword in str(s.get("industries", "")).lower()
                        or keyword in str(s.get("irl_description", "")).lower()
                        or keyword in str(s.get("crl_description", "")).lower()
                        for keyword in keywords if len(keyword) > 2  # Слова длиннее 2 символов (для "API")
                    )
                ]
        elif key == "year":
            # Обрабатываем как список, так и строку
            if isinstance(value, str):
                value = [value]
            
            if isinstance(value, list) and len(value) > 0:
                # Парсим различные форматы: ["2020","2021"], ["2020,2021"], ["2020-2025"]
                years = []
                for v in value:
                    v_str = str(v).strip()
                    if not v_str or v_str == "":
                        continue
                    
                    if '-' in v_str:
                        # Диапазон: "2020-2025" -> [2020,2021,2022,2023,2024,2025]
                        try:
                            parts = v_str.split('-')
                            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                                start, end = int(parts[0].strip()), int(parts[1].strip())
                                years.extend([str(y) for y in range(start, end + 1)])
                        except Exception as e:
                            logger.warning(f"Ошибка парсинга диапазона годов {v_str}: {e}")
                    elif ',' in v_str:
                        # Список через запятую: "2020,2021,2022" -> [2020,2021,2022]
                        years.extend([y.strip() for y in v_str.split(',') if y.strip().isdigit()])
                    elif v_str.isdigit():
                        # Одно число: "2020" -> [2020]
                        years.append(v_str)
                
                if years:
                    filtered = [s for s in filtered if str(s.get("year", "")) in years]
            elif not isinstance(value, list) and value and str(value).isdigit():
                filtered = [s for s in filtered if str(s.get("year", "")) == str(value)]
        elif key == "stage":
            if isinstance(value, list) and len(value) > 0:
                filtered = [s for s in filtered if determine_stage(s) in value]
            elif not isinstance(value, list) and value and str(value).strip():
                filtered = [s for s in filtered if determine_stage(s) == value]
        elif key == "min_profit":
            # Фильтр по минимальной прибыли
            if value and (isinstance(value, (int, float)) and value > 0):
                filtered = [s for s in filtered if get_max_profit(s) >= value]
        elif key == "cluster":
            # Фильтр по кластеру (более точное определение сферы)
            if isinstance(value, list) and len(value) > 0:
                filtered = [s for s in filtered if any(c.strip().lower() in str(s.get("cluster", "")).lower() for c in value)]
            elif not isinstance(value, list) and value and str(value).strip():
                filtered = [s for s in filtered if value.strip().lower() in str(s.get("cluster", "")).lower()]
        elif key == "status":
            # Фильтр по статусу организации
            if isinstance(value, list) and len(value) > 0:
                filtered = [s for s in filtered if any(st.strip().lower() in str(s.get("status", "")).lower() for st in value)]
            elif not isinstance(value, list) and value and str(value).strip():
                filtered = [s for s in filtered if value.strip().lower() in str(s.get("status", "")).lower()]
        elif key == "has_patents":
            # Фильтр по наличию патентов (только если явно указано True или False)
            if value is True:
                filtered = [s for s in filtered if s.get("patents", "").strip() != ""]
            elif value is False:
                filtered = [s for s in filtered if s.get("patents", "").strip() == ""]
            # Если None - не фильтруем
        elif key == "country":
            if isinstance(value, list) and len(value) > 0:
                filtered = [s for s in filtered if any(c.strip().lower() in str(s.get("country", "")).lower() for c in value)]
            elif not isinstance(value, list) and value and str(value).strip():
                filtered = [s for s in filtered if value.strip().lower() in str(s.get("country", "")).lower()]
        elif key in ["trl", "irl", "mrl", "crl"]:
            # Обрабатываем как список, так и строку
            if isinstance(value, str):
                value = [value]
            
            if isinstance(value, list) and len(value) > 0:
                # Парсим различные форматы: ["1","2","3"], ["1,2,3"], ["1-3"]
                levels = []
                for v in value:
                    v_str = str(v).strip()
                    if not v_str or v_str == "":
                        continue
                    
                    if '-' in v_str:
                        # Диапазон: "4-9" -> [4,5,6,7,8,9]
                        try:
                            parts = v_str.split('-')
                            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                                start, end = int(parts[0].strip()), int(parts[1].strip())
                                levels.extend(range(start, end + 1))
                        except Exception as e:
                            logger.warning(f"Ошибка парсинга диапазона {v_str}: {e}")
                    elif ',' in v_str:
                        # Список через запятую: "4,5,6" -> [4,5,6]
                        for x in v_str.split(','):
                            if x.strip().isdigit():
                                levels.append(int(x.strip()))
                    elif v_str.isdigit():
                        # Одно число: "4" -> [4]
                        levels.append(int(v_str))
                
                if levels:
                    filtered = [s for s in filtered if extract_level_value(s.get(key, 0)) in levels]
            elif not isinstance(value, list) and value and str(value).isdigit():
                filtered = [s for s in filtered if extract_level_value(s.get(key, 0)) == int(value)]
        
        # Логируем результат фильтрации
        count_after = len(filtered)
        if count_before != count_after:
            logger.info(f"🔍 Фильтр '{key}' (значение: {value}): {count_before} -> {count_after} стартапов")

    logger.info(f"🔍 После всех фильтров осталось: {len(filtered)} стартапов")
    
    available = [s for s in filtered if s.get("id", "") not in shown_startups]
    if len(available) < count:
        shown_startups.clear()
        available = filtered

    selected = random.sample(available, min(count, len(available)))
    for s in selected:
        shown_startups.add(s.get("id", ""))
    return selected

