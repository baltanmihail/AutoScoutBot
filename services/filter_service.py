"""
Модуль для применения фильтров к стартапам
Вынесен из bot.py для переиспользования в RAG
"""
from logger import logger


def parse_level_values(value) -> list:
    """Парсинг значений уровней"""
    if isinstance(value, str):
        value = [value]
    
    if not isinstance(value, list) or len(value) == 0:
        return []
    
    levels = []
    for v in value:
        v_str = str(v).strip()
        if not v_str or v_str == "":
            continue
        
        if '-' in v_str:
            try:
                parts = v_str.split('-')
                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                    start, end = int(parts[0].strip()), int(parts[1].strip())
                    levels.extend(range(start, end + 1))
            except Exception as e:
                logger.warning(f"Ошибка парсинга диапазона {v_str}: {e}")
        elif ',' in v_str:
            for x in v_str.split(','):
                if x.strip().isdigit():
                    levels.append(int(x.strip()))
        elif v_str.isdigit():
            levels.append(int(v_str))
    
    return levels


def parse_year_values(value) -> list:
    """Парсинг значений годов"""
    if isinstance(value, str):
        value = [value]
    
    if not isinstance(value, list) or len(value) == 0:
        return []
    
    years = []
    for v in value:
        v_str = str(v).strip()
        if not v_str or v_str == "":
            continue
        
        if '-' in v_str:
            try:
                parts = v_str.split('-')
                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                    start, end = int(parts[0].strip()), int(parts[1].strip())
                    years.extend([str(y) for y in range(start, end + 1)])
            except Exception as e:
                logger.warning(f"Ошибка парсинга диапазона годов {v_str}: {e}")
        elif ',' in v_str:
            years.extend([y.strip() for y in v_str.split(',') if y.strip().isdigit()])
        elif v_str.isdigit():
            years.append(v_str)
    
    return years


def apply_filters(startups: list, filters: dict, user_request: str = "", 
                  extract_level_value=None, get_max_profit=None, 
                  determine_stage=None, analyze_startup=None,
                  max_profit_limit=None) -> list:
    """
    Применение фильтров к списку стартапов
    Используется как в обычном поиске, так и в RAG
    
    Параметры:
    - extract_level_value: функция для извлечения уровня из значения
    - get_max_profit: функция для получения максимальной прибыли
    - determine_stage: функция для определения стадии
    - analyze_startup: функция для анализа стартапа
    - max_profit_limit: максимальная прибыль (для исключения зрелых компаний)
    """
    from logger import logger
    
    filtered = startups.copy()
    
    # Сначала применяем max_profit_limit если передан
    if max_profit_limit and get_max_profit:
        count_before = len(filtered)
        filtered = [s for s in filtered if get_max_profit(s) <= max_profit_limit]
        count_after = len(filtered)
        if count_before != count_after:
            logger.info(f"🔍 Фильтр 'max_profit_limit' (<= {max_profit_limit/1_000_000:.0f}M): {count_before} -> {count_after}")
    
    for key, value in filters.items():
        if isinstance(value, list) and len(value) <= 0:
            continue
        
        count_before = len(filtered)

        if key == "DeepTech":
            if value and str(value).strip() and str(value).strip().isdigit():
                filtered = [s for s in filtered if analyze_startup(s)["DeepTech"] >= int(value)]
        
        elif key == "GenAI":
            if value and str(value).strip() in ["есть", "нет"]:
                filtered = [s for s in filtered if analyze_startup(s)["GenAI"] == value]
        
        elif key == "WOW":
            if value and str(value).strip() in ["да", "нет"]:
                filtered = [s for s in filtered if analyze_startup(s)["WOW"] == value]
        
        elif key == "cluster":
            if isinstance(value, list) and len(value) > 0:
                filtered = [s for s in filtered if any(c.strip().lower() in str(s.get("cluster", "")).lower() for c in value)]
            elif not isinstance(value, list) and value and str(value).strip():
                filtered = [s for s in filtered if value.strip().lower() in str(s.get("cluster", "")).lower()]
        
        elif key == "status":
            if isinstance(value, list) and len(value) > 0:
                filtered = [s for s in filtered if any(st.strip().lower() in str(s.get("status", "")).lower() for st in value)]
            elif not isinstance(value, list) and value and str(value).strip():
                filtered = [s for s in filtered if value.strip().lower() in str(s.get("status", "")).lower()]
        
        elif key == "has_patents":
            if value is True:
                filtered = [s for s in filtered if s.get("patents", "").strip() != ""]
            elif value is False:
                filtered = [s for s in filtered if s.get("patents", "").strip() == ""]
        
        elif key == "year":
            years = parse_year_values(value)
            if years:
                filtered = [s for s in filtered if str(s.get("year", "")) in years]
        
        elif key == "stage":
            if isinstance(value, list) and len(value) > 0:
                filtered = [s for s in filtered if determine_stage(s) in value]
            elif not isinstance(value, list) and value and str(value).strip():
                filtered = [s for s in filtered if determine_stage(s) == value]
        
        elif key == "min_profit":
            if value and (isinstance(value, (int, float)) and value > 0):
                filtered = [s for s in filtered if get_max_profit(s) >= value]
        
        elif key == "max_profit_limit":
            # Ограничение сверху (для исключения зрелых компаний)
            if value and (isinstance(value, (int, float)) and value > 0):
                filtered = [s for s in filtered if get_max_profit(s) <= value]
        
        elif key == "country":
            if isinstance(value, list) and len(value) > 0:
                filtered = [s for s in filtered if any(c.strip().lower() in str(s.get("country", "")).lower() for c in value)]
            elif not isinstance(value, list) and value and str(value).strip():
                filtered = [s for s in filtered if value.strip().lower() in str(s.get("country", "")).lower()]
        
        elif key in ["trl", "irl", "mrl", "crl"]:
            levels = parse_level_values(value)
            if levels:
                filtered = [s for s in filtered if extract_level_value(s.get(key, 0)) in levels]
        
        # Логируем результат
        count_after = len(filtered)
        if count_before != count_after:
            logger.info(f"🔍 Фильтр '{key}': {count_before} -> {count_after}")

    return filtered

