"""
Утилиты для работы со стартапами
"""
import pandas as pd
import re
import hashlib
import random
from datetime import datetime
from logger import logger
from constants.constants import MAIN_CATEGORIES, MAIN_REGIONS
from config import SKOLKOVO_DATABASE_PATH


def format_date(date_str: str) -> str:
    try:
        if not date_str or pd.isna(date_str):
            return ""
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%d.%m.%Y")
            except ValueError:
                continue
        return date_str
    except Exception:
        return date_str


def load_skolkovo_database():
    """Загружает базу данных Сколково и возвращает список словарей и словарь фильтров"""
    try:
        df = pd.read_csv(SKOLKOVO_DATABASE_PATH, encoding="utf-8", dtype=str)

        column_mapping = {
            "Название компании": "name",
            "Сайт": "website",
            "Описание проектов": "description",
            "Описание компании": "company_description",
            "Описание продуктов": "product_description",
            "Год основания": "year",
            "Сферы деятельности": "category",
            "Регионы присутствия": "country",
            "TRL (по продуктам)": "trl",
            "IRL - Уровень": "irl",
            "IRL - Описание": "irl_description",
            "MRL (по продуктам)": "mrl",
            "CRL - Уровень": "crl",
            "CRL - Описание": "crl_description",
            "Статус организации": "status",
            "Кластер": "cluster",
            "Патенты": "patents",
            "Названия продуктов": "product_names",
            "Названия проектов": "project_names",
            "Технологии проекта": "technologies",
            "Отрасли применения": "industries",
            "Выручка 2025": "revenue_2025",
            "Прибыль 2025": "profit_2025",
            "Выручка 2024": "revenue_2024",
            "Прибыль 2024": "profit_2024",
            "Выручка 2023": "revenue_2023",
            "Прибыль 2023": "profit_2023",
            "Выручка 2022": "revenue_2022",
            "Прибыль 2022": "profit_2022",
            "Выручка 2021": "revenue_2021",
            "Прибыль 2021": "profit_2021",
            "Выручка 2020": "revenue_2020",
            "Прибыль 2020": "profit_2020",
            "Url": "sk_url",
            "ИНН": "inn",
            "ОГРН": "ogrn",
            "Полное юр. название": "full_legal_name",
        }
        for ru, en in column_mapping.items():
            if ru in df.columns:
                df.rename(columns={ru: en}, inplace=True)

        if "name" in df.columns:
            df["id"] = df["name"].apply(lambda x: hashlib.md5(str(x).encode("utf-8")).hexdigest())
        else:
            df["id"] = df.apply(
                lambda row: hashlib.md5(str(row[0] + str(row[1])).encode("utf-8")).hexdigest(), axis=1
            )

        df.fillna("", inplace=True)

        years_available = sorted(
            set(df["year"].astype(str).unique()),
            key=lambda x: int(x) if x.isdigit() else 0,
            reverse=True,
        )
        years_filtered = [y for y in years_available if y and y.isdigit() and 2000 <= int(y) <= 2025][:15]

        available_filters = {
            "category": MAIN_CATEGORIES,
            "year": years_filtered,
            "stage": ["Pre-seed", "Seed", "Round A", "Round B", "Неизвестно"],
            "country": MAIN_REGIONS,
            "trl": list(range(1, 10)),
            "irl": list(range(1, 10)),
            "mrl": list(range(1, 10)),
            "crl": list(range(1, 10)),
        }

        return df.to_dict("records"), available_filters
    except Exception as e:
        logger.error(f"Ошибка загрузки базы Сколково: {str(e)}")
        return None, {}


def extract_level_value(level_str):
    """
    Извлекает максимальное значение уровня из строки
    Обрабатывает множественные значения (например: "3: ...; 2: ...; 7: ...")
    """
    try:
        if pd.isna(level_str) or level_str == "" or level_str == 0:
            return 0
        
        level_str = str(level_str).strip()
        
        # Если это просто число - возвращаем его
        if level_str.isdigit():
            return int(level_str)
        
        # Ищем все числа в начале строки или после точки с запятой
        # Паттерны: "N:" или "; N:" где N - число
        matches = re.findall(r'(?:^|;\s*)(\d+)\s*:', level_str)
        
        if matches:
            # Берем максимальное значение (самый высокий уровень)
            levels = [int(m) for m in matches if 0 <= int(m) <= 9]  # Только валидные уровни 0-9
            if levels:
                max_level = max(levels)
                # Логируем только если нашли множественные значения
                if len(levels) > 1:
                    logger.info(f"📊 Найдены уровни {levels}, выбран максимум: {max_level}")
                return max_level
        
        # Fallback: ищем первое число от 0 до 9
        match = re.search(r'[0-9]', level_str)
        if match:
            return int(match.group())
        
        return 0
    except Exception as e:
        logger.warning(f"Ошибка парсинга уровня '{str(level_str)[:50]}': {e}")
        return 0


def parse_profit(profit_str):
    """Парсит строку с прибылью и возвращает число в рублях"""
    try:
        if not profit_str or profit_str.strip().lower() in ["", "н/д", "н/а", "-", "0"]:
            return 0
        clean_str = profit_str.replace(" ", "").replace(",", ".")
        if "млн" in clean_str.lower():
            value = float(re.search(r"[\d.]+", clean_str).group())
            return int(value * 1_000_000)
        elif "тыс" in clean_str.lower():
            value = float(re.search(r"[\d.]+", clean_str).group())
            return int(value * 1_000)
        else:
            return float(clean_str)
    except:
        return 0


def get_max_profit(startup):
    """Возвращает максимальную прибыль за все годы"""
    max_profit = 0
    for year in ["2025", "2024", "2023", "2022", "2021", "2020"]:
        profit = parse_profit(startup.get(f"profit_{year}", ""))
        if profit > max_profit:
            max_profit = profit
    return max_profit


def determine_stage(startup):
    """
    Определяет стадию стартапа
    
    Строгая логика для различения стартапов и зрелых компаний:
    - Pre-seed: < 1M
    - Seed: 1-5M
    - Round A: 5-20M (настоящие стартапы)
    - Round B: 20-100M (уже не стартапы, средний бизнес)
    - Round C+: > 100M (крупные компании)
    """
    try:
        max_profit = get_max_profit(startup)
        trl = extract_level_value(startup.get("trl", 0))
        irl = extract_level_value(startup.get("irl", 0))

        if max_profit <= 0:
            return "Pre-seed"
        elif max_profit < 1_000_000:
            return "Pre-seed"
        elif max_profit < 5_000_000:
            return "Seed"
        elif max_profit < 20_000_000:
            return "Round A"
        elif max_profit < 100_000_000:
            return "Round B"
        else:
            return "Round C+"
    except Exception as e:
        logger.error(f"Ошибка определения стадии: {str(e)}")
        return "Неизвестно"


def calculate_financial_stability(startup: dict) -> dict:
    """Расчет финансовой устойчивости на основе данных за 2020-2024"""
    try:
        profits = []
        revenues = []
        years_data = []
        
        for year in ["2024", "2023", "2022", "2021", "2020"]:
            profit = parse_profit(startup.get(f"profit_{year}", ""))
            revenue = parse_profit(startup.get(f"revenue_{year}", ""))
            if profit > 0:
                profits.append(profit)
                years_data.append(year)
            if revenue > 0:
                revenues.append(revenue)
        
        # Анализ тренда прибыли
        profit_trend = "стабильный"
        if len(profits) >= 3:
            # Проверяем тренд на основе последних 3 лет
            if all(profits[i] > profits[i+1] for i in range(min(2, len(profits)-1))):
                profit_trend = "растущий"
            elif all(profits[i] < profits[i+1] for i in range(min(2, len(profits)-1))):
                profit_trend = "падающий"
            else:
                # Проверяем волатильность
                changes = [abs(profits[i] - profits[i+1]) / profits[i+1] for i in range(len(profits)-1) if profits[i+1] > 0]
                avg_change = sum(changes) / len(changes) if changes else 0
                if avg_change > 0.5:
                    profit_trend = "нестабильный"
        elif len(profits) >= 2:
            if profits[0] > profits[1]:
                profit_trend = "растущий"
            elif profits[0] < profits[1]:
                profit_trend = "падающий"
        
        # Средняя прибыль
        avg_profit = sum(profits) / len(profits) if profits else 0
        
        # Рентабельность (если есть данные)
        profitability = 0
        if revenues and profits and len(revenues) == len(profits):
            avg_revenue = sum(revenues) / len(revenues)
            if avg_revenue > 0:
                profitability = (avg_profit / avg_revenue) * 100
        
        # Оценка финансового здоровья
        financial_health = "слабое"
        if len(profits) >= 3 and profit_trend == "растущий" and avg_profit > 1_000_000:
            financial_health = "отличное"
        elif len(profits) >= 2 and avg_profit > 500_000:
            financial_health = "хорошее"
        elif len(profits) >= 1 and avg_profit > 0:
            financial_health = "среднее"
        
        return {
            "profit_trend": profit_trend,
            "avg_profit": avg_profit,
            "profitability": profitability,
            "years_with_data": len(profits),
            "financial_health": financial_health,
            "years_list": years_data
        }
    except Exception as e:
        logger.error(f"Ошибка расчета финансовой устойчивости: {e}")
        return {
            "profit_trend": "неизвестно", 
            "avg_profit": 0, 
            "profitability": 0, 
            "years_with_data": 0,
            "financial_health": "неизвестно",
            "years_list": []
        }


def calculate_patent_score(startup: dict) -> dict:
    """Оценка патентной защищенности"""
    patents = str(startup.get("patents", "")).strip()
    
    if not patents:
        return {"has_patents": False, "patent_score": 0, "patent_comment": ""}
    
    # Подсчет количества патентов (примерно)
    patent_count = len([p for p in patents.split(";") if p.strip()])
    
    patent_score = 0
    if patent_count >= 10:
        patent_score = 3
        comment = f"Высокая патентная защита ({patent_count}+ патентов)"
    elif patent_count >= 5:
        patent_score = 2
        comment = f"Средняя патентная защита (~{patent_count} патентов)"
    else:
        patent_score = 1
        comment = f"Базовая патентная защита (~{patent_count} патентов)"
    
    return {
        "has_patents": True,
        "patent_score": patent_score,
        "patent_comment": comment
    }


def analyze_startup(startup: dict):
    """Проводит комплексный анализ стартапа"""
    try:
        trl_raw = startup.get("trl", 0)
        irl_raw = startup.get("irl", 0)
        mrl_raw = startup.get("mrl", 0)
        crl_raw = startup.get("crl", 0)
        
        trl = extract_level_value(trl_raw)
        irl = extract_level_value(irl_raw)
        mrl = extract_level_value(mrl_raw)
        crl = extract_level_value(crl_raw)
        
        # Отладка для первых стартапов
        startup_name = startup.get("name", "unknown")
        if trl == 0 and trl_raw and str(trl_raw).strip():
            logger.warning(f"⚠️ TRL=0 для '{startup_name}', raw='{str(trl_raw)[:100]}'")
        
        levels = [trl, irl, mrl, crl]
        non_zero_levels = [x for x in levels if x > 0]
        avg_level = sum(non_zero_levels) / len(non_zero_levels) if non_zero_levels else 0
        high_level_count = sum(1 for lvl in non_zero_levels if lvl >= 7)
        very_high_level_count = sum(1 for lvl in non_zero_levels if lvl >= 8)

        # НОВАЯ логика DeepTech (более мягкая, учитывает специфику стартапов)
        # DeepTech = 3: avg >= 6.0 ИЛИ 2+ показателя >= 7 ИЛИ 1+ показатель >= 8
        if avg_level >= 6.0 or very_high_level_count >= 1 or high_level_count >= 2:
            deeptech = 3
        # DeepTech = 2: avg >= 4.0 ИЛИ 1+ показатель >= 6 ИЛИ 2+ показателя >= 5
        elif avg_level >= 4.0 or sum(1 for lvl in non_zero_levels if lvl >= 6) >= 1 or sum(1 for lvl in non_zero_levels if lvl >= 5) >= 2:
            deeptech = 2
        # DeepTech = 1: все остальные
        else:
            deeptech = 1

        # Анализ описаний (компания + проекты + продукты + технологии)
        description = str(startup.get("company_description", "")).lower()
        if not description:
            description = str(startup.get("description", "")).lower()
        description += " " + str(startup.get("product_description", "")).lower()
        description += " " + str(startup.get("technologies", "")).lower()
        description += " " + str(startup.get("product_names", "")).lower()
        description += " " + str(startup.get("project_names", "")).lower()
        
        genai_keywords = [
            "искусственный интеллект", "нейросеть", "машинное обучение",
            "ai", "generative ai", "llm", "gpt", "нейронная сеть", "ии",
            "artificial intelligence", "deep learning", "ml", "neural network"
        ]
        genai = "есть" if any(kw in description for kw in genai_keywords) else "нет"
        
        # НОВАЯ логика WOW (более строгая)
        wow = "да" if deeptech == 3 and genai == "есть" else "нет"

        # НОВАЯ логика Светофора (более мягкая, меньше красных)
        financial = calculate_financial_stability(startup)
        max_profit = get_max_profit(startup)
        patent_info = calculate_patent_score(startup)
        stage = determine_stage(startup)
        patent_count = patent_info.get("patent_score", 0)
        
        # Зрелые компании (Round B/C+)
        if stage in ["Round B", "Round C+"]:
            if (max_profit > 20_000_000 and 
                financial["profit_trend"] in ["растущий", "стабильный"] and 
                (deeptech >= 2 or genai == "есть")):
                traffic_light = 3  # Зеленый
            elif max_profit > 10_000_000 or deeptech >= 2:
                traffic_light = 2  # Желтый
            else:
                traffic_light = 2  # Желтый по умолчанию для зрелых компаний
        
        # Настоящие стартапы (Pre-seed, Seed, Round A)
        else:
            # Зеленый: WOW-эффект + хорошие финансы
            if (deeptech == 3 and genai == "есть" and 
                financial["profit_trend"] in ["растущий", "стабильный"]):
                if stage == "Round A" and max_profit > 3_000_000:
                    traffic_light = 3
                elif stage == "Seed" and max_profit > 500_000:
                    traffic_light = 3
                else:
                    traffic_light = 2  # Желтый если прибыль низкая
            
            # Желтый: средняя/высокая технологичность ИЛИ AI ИЛИ патенты
            elif (deeptech >= 2 or genai == "есть"):
                if stage == "Round A" and max_profit > 1_000_000:
                    traffic_light = 2
                elif stage == "Seed" and max_profit > 100_000:
                    traffic_light = 2
                elif patent_count >= 2:
                    traffic_light = 2  # Желтый за патенты
                elif genai == "есть":
                    traffic_light = 2  # Желтый за AI
                else:
                    traffic_light = 1  # Красный если нет прибыли и патентов
            
            # Красный: низкая технологичность + нет AI + низкая прибыль
            else:
                traffic_light = 1

        comments = []
        
        # Базовая информация
        cluster = startup.get("cluster", "")
        if cluster:
            comments.append(f"📌 Кластер: {cluster}")
        
        status = startup.get("status", "")
        if status:
            comments.append(f"📊 Статус: {status}")
        
        # Технологии проекта (если есть)
        technologies = startup.get("technologies", "")
        if technologies and len(technologies) > 10:
            tech_short = technologies[:100] + "..." if len(technologies) > 100 else technologies
            comments.append(f"🔧 Технологии: {tech_short}")
        
        comments.append(f"🔬 Уровни зрелости: TRL={trl}, IRL={irl}, MRL={mrl}, CRL={crl}")
        if non_zero_levels:
            comments.append(f"📈 Средний уровень: {avg_level:.1f}")
        
        # Технологичность
        if deeptech == 3:
            comments.append("⭐ Высокий уровень технологичности")
        elif deeptech == 2:
            comments.append("✓ Средний уровень технологичности")
        else:
            comments.append("• Низкий уровень технологичности")
        
        # ИИ
        if genai == "есть":
            comments.append("🤖 Использует технологии ИИ")
        
        # WOW-эффект
        if wow == "да":
            comments.append("💫 Комбинация технологичности и ИИ создает WOW-эффект")
        
        # Патенты
        patent_info = calculate_patent_score(startup)
        if patent_info["has_patents"]:
            comments.append(f"📜 {patent_info['patent_comment']}")
        
        # Финансовый анализ
        financial = calculate_financial_stability(startup)
        if financial["years_with_data"] > 0:
            comments.append(f"💰 Финансовая динамика: {financial['profit_trend']} ({financial['years_with_data']} лет данных)")
            if financial["avg_profit"] > 0:
                profit_str = f"{financial['avg_profit'] / 1_000_000:.2f} млн руб" if financial['avg_profit'] >= 1_000_000 else f"{financial['avg_profit'] / 1_000:.1f} тыс руб"
                comments.append(f"📊 Средняя прибыль: {profit_str}")
            if financial["profitability"] > 0:
                comments.append(f"📈 Рентабельность: {financial['profitability']:.1f}%")

        max_profit = get_max_profit(startup)
        if max_profit > 0:
            if max_profit >= 1_000_000:
                profit_str = f"{max_profit / 1_000_000:.2f} млн руб"
            elif max_profit >= 1_000:
                profit_str = f"{max_profit / 1_000:.1f} тыс руб"
            else:
                profit_str = f"{max_profit:.0f} руб"
            comments.append(f"💵 Максимальная годовая прибыль: {profit_str}")
        else:
            comments.append("⚠️ Прибыль не подтверждена")

        traffic_light_map = {1: "🔴 Красный (нет)", 2: "🟡 Желтый (возможно)", 3: "🟢 Зеленый (да)"}
        comments.append(f"🚦 Оценка: {traffic_light_map[traffic_light]}")

        comment = "\n".join(comments)
        return {
            "DeepTech": deeptech,
            "GenAI": genai,
            "WOW": wow,
            "TrafficLight": traffic_light,
            "Comments": comment,
            "FinancialStability": financial["profit_trend"],
            "AvgProfit": financial["avg_profit"],
            "FinancialHealth": financial.get("financial_health", "неизвестно"),
        }
    except Exception as e:
        logger.error(f"Ошибка анализа стартапа: {str(e)}")
        return {
            "DeepTech": random.randint(1, 3),
            "GenAI": "есть" if random.random() > 0.5 else "нет",
            "WOW": "да" if random.random() > 0.5 else "нет",
            "TrafficLight": random.randint(1, 3),
            "Comments": f"Ошибка анализа: {str(e)}",
            "FinancialStability": "неизвестно",
            "AvgProfit": 0,
            "FinancialHealth": "неизвестно",
        }


