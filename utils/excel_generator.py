"""
Генерация Excel и CSV файлов с данными о стартапах
"""
import csv
import io
import pandas as pd
from utils.startup_utils import (
    determine_stage, extract_level_value, get_max_profit,
    calculate_patent_score
)
from utils.formatters import remove_emojis


def generate_csv(startups: list):
    """Генерирует CSV файл с данными о стартапах"""
    filename = "startups_report.csv"
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Название",
                "Сайт",
                "Описание",
                "Год создания",
                "Стадия",
                "Направление",
                "Регион",
                "DeepTech",
                "GenAI",
                "ВАУ",
                "Оценка Светофор",
                "TRL",
                "IRL",
                "MRL",
                "CRL",
                "Средняя прибыль (млн руб)",
                "Максимальная прибыль (млн руб)",
                "Аргумент",
                "ИНН",
                "ОГРН",
            ]
        )
        for s in startups:
            name = s.get("name", "Название не указано")
            website = s.get("website", "")
            description = s.get("company_description", "") or s.get("description", "Описание отсутствует")
            cluster = s.get("cluster", "")
            year = s.get("year", "")
            stage = determine_stage(s)
            category = s.get("category", "")
            country = s.get("country", "")
            status = s.get("status", "")
            analysis = s.get("analysis", {})
            comments = remove_emojis(analysis.get("Comments", ""))  # Убираем смайлики
            traffic_light = analysis.get("TrafficLight", "")
            financial_health = analysis.get("FinancialStability", "")
            
            # Уровни зрелости
            trl = extract_level_value(s.get("trl", 0))
            irl = extract_level_value(s.get("irl", 0))
            mrl = extract_level_value(s.get("mrl", 0))
            crl = extract_level_value(s.get("crl", 0))
            
            # Финансы
            avg_profit = analysis.get("AvgProfit", 0) / 1_000_000 if analysis.get("AvgProfit", 0) else 0
            max_profit = get_max_profit(s) / 1_000_000 if get_max_profit(s) else 0
            profitability = analysis.get("Profitability", 0)
            
            # Патенты
            patent_info = calculate_patent_score(s)
            patent_count = patent_info.get("patent_score", 0)
            
            # Соответствие запросу (RAG similarity) - точное значение
            rag_similarity = analysis.get("rag_similarity", 0)
            
            # Технологии
            technologies = s.get("technologies", "")[:300]
            
            # Аналитический обзор (полная версия)
            ai_recommendation = analysis.get("AIRecommendation", "")
            
            inn = s.get("inn", "")
            ogrn = s.get("ogrn", "")
            
            # Формируем расширенный "Аргумент" со всей дополнительной информацией
            extended_argument = comments
            if cluster:
                extended_argument += f"\n\nКластер: {cluster}"
            if status:
                extended_argument += f"\nСтатус: {status}"
            if technologies:
                extended_argument += f"\nТехнологии: {technologies}"
            if profitability > 0:
                extended_argument += f"\nРентабельность: {profitability:.1f}%"
            if financial_health:
                extended_argument += f"\nФинансовое здоровье: {financial_health}"
            if patent_count > 0:
                extended_argument += f"\nПатенты: {patent_count}"
            if rag_similarity > 0:
                extended_argument += f"\nСхожесть с запросом: {rag_similarity:.3f}"
            if ai_recommendation:
                extended_argument += f"\n\nАналитический обзор:\n{ai_recommendation}"
            
            writer.writerow(
                [
                    name,
                    website,
                    description,
                    year,
                    stage,
                    category,
                    country,
                    analysis.get("DeepTech", ""),
                    analysis.get("GenAI", ""),
                    analysis.get("WOW", ""),
                    traffic_light,
                    trl,
                    irl,
                    mrl,
                    crl,
                    f"{avg_profit:.2f}" if avg_profit > 0 else "",
                    f"{max_profit:.2f}" if max_profit > 0 else "",
                    extended_argument,
                    inn,
                    ogrn,
                ]
            )
    return filename, len(startups)


def generate_excel(startups: list) -> io.BytesIO:
    """Генерирует Excel файл с данными о стартапах"""
    data = []
    for s in startups:
        name = s.get("name", "Название не указано")
        website = s.get("website", "")
        description = s.get("company_description", "") or s.get("description", "Описание отсутствует")
        cluster = s.get("cluster", "")
        year = s.get("year", "")
        stage = determine_stage(s)
        category = s.get("category", "")
        country = s.get("country", "")
        analysis = s.get("analysis", {})
        comments = remove_emojis(analysis.get("Comments", ""))  # Убираем смайлики
        traffic_light = analysis.get("TrafficLight", "")
        financial_health = analysis.get("FinancialStability", "")
        inn = s.get("inn", "")
        ogrn = s.get("ogrn", "")
        # Уровни зрелости
        trl = extract_level_value(s.get("trl", 0))
        irl = extract_level_value(s.get("irl", 0))
        mrl = extract_level_value(s.get("mrl", 0))
        crl = extract_level_value(s.get("crl", 0))
        
        # Финансы
        avg_profit = analysis.get("AvgProfit", 0) / 1_000_000 if analysis.get("AvgProfit", 0) else 0
        max_profit = get_max_profit(s) / 1_000_000 if get_max_profit(s) else 0
        profitability = analysis.get("Profitability", 0)
        
        # Патенты
        patent_info = calculate_patent_score(s)
        patent_count = patent_info.get("patent_score", 0)
        
        # Соответствие запросу (RAG similarity)
        rag_similarity = analysis.get("rag_similarity", 0)
        similarity_percent = int(rag_similarity * 100) if rag_similarity else 0
        
        # Технологии
        technologies = s.get("technologies", "")[:500]  # Ограничиваем длину
        
        # Аналитический обзор (полная версия)
        ai_recommendation = analysis.get("AIRecommendation", "")
        
        status = s.get("status", "")
        
        # Формируем расширенный "Аргумент" со всей дополнительной информацией
        extended_argument = comments
        if cluster:
            extended_argument += f"\n\nКластер: {cluster}"
        if status:
            extended_argument += f"\nСтатус: {status}"
        if technologies:
            extended_argument += f"\nТехнологии: {technologies}"
        if profitability > 0:
            extended_argument += f"\nРентабельность: {profitability:.1f}%"
        if financial_health:
            extended_argument += f"\nФинансовое здоровье: {financial_health}"
        if patent_count > 0:
            extended_argument += f"\nПатенты: {patent_count}"
        if similarity_percent > 0:
            extended_argument += f"\nСоответствие запросу: {similarity_percent}%"
        if ai_recommendation:
            extended_argument += f"\n\nАналитический обзор:\n{ai_recommendation}"
        
        data.append(
            {
                "Название": name,
                "Сайт": website,
                "Описание": description,
                "Год создания": year,
                "Стадия": stage,
                "Направление": category,
                "Регион": country,
                "DeepTech": analysis.get("DeepTech", ""),
                "GenAI": analysis.get("GenAI", ""),
                "ВАУ": analysis.get("WOW", ""),
                "Оценка Светофор": traffic_light,
                "TRL": trl,
                "IRL": irl,
                "MRL": mrl,
                "CRL": crl,
                "Средняя прибыль (млн руб)": f"{avg_profit:.2f}" if avg_profit > 0 else "",
                "Максимальная прибыль (млн руб)": f"{max_profit:.2f}" if max_profit > 0 else "",
                "Аргумент": extended_argument,
                "ИНН": inn,
                "ОГРН": ogrn,
            }
        )
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Startups")
    output.seek(0)
    return output


