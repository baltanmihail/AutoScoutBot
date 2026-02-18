"""
ML Scoring bridge -- connects trained XGBoost models to the bot.

Usage in bot code:
    from scoring.ml_scoring import ml_analyze_startup
    result = ml_analyze_startup(startup_dict)
    # -> {"DeepTech": 3, "GenAI": "есть", "WOW": "да", "TrafficLight": 3,
    #     "Comments": "...", "ml_scores": {...}, "ml_available": True}

Falls back gracefully if models are not trained yet.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Human-readable Russian labels for all 39 ML features
FEATURE_LABELS_RU = {
    # Financial per-year (12)
    "log_revenue_2025": ("Выручка 2025", "логарифм выручки за 2025 г."),
    "log_revenue_2024": ("Выручка 2024", "логарифм выручки за 2024 г."),
    "log_revenue_2023": ("Выручка 2023", "логарифм выручки за 2023 г."),
    "log_revenue_2022": ("Выручка 2022", "логарифм выручки за 2022 г."),
    "log_revenue_2021": ("Выручка 2021", "логарифм выручки за 2021 г."),
    "log_revenue_2020": ("Выручка 2020", "логарифм выручки за 2020 г."),
    "log_profit_2025": ("Прибыль 2025", "логарифм прибыли за 2025 г."),
    "log_profit_2024": ("Прибыль 2024", "логарифм прибыли за 2024 г."),
    "log_profit_2023": ("Прибыль 2023", "логарифм прибыли за 2023 г."),
    "log_profit_2022": ("Прибыль 2022", "логарифм прибыли за 2022 г."),
    "log_profit_2021": ("Прибыль 2021", "логарифм прибыли за 2021 г."),
    "log_profit_2020": ("Прибыль 2020", "логарифм прибыли за 2020 г."),
    # Financial derived (6)
    "max_revenue_log": ("Макс. выручка", "максимальная выручка за все годы"),
    "max_profit_log": ("Макс. прибыль", "максимальная прибыль за все годы"),
    "revenue_trend": ("Тренд выручки", "рост или падение выручки"),
    "profit_margin": ("Рентабельность", "средняя маржа прибыли"),
    "revenue_stability": ("Стабильность выручки", "постоянство доходов"),
    "years_with_revenue": ("Лет с выручкой", "количество лет с ненулевой выручкой"),
    # Technology (8)
    "trl": ("TRL", "уровень готовности технологии"),
    "irl": ("IRL", "уровень инвестиционной готовности"),
    "mrl": ("MRL", "уровень производственной готовности"),
    "crl": ("CRL", "уровень коммерциализации"),
    "patent_count": ("Патенты", "количество зарегистрированных патентов"),
    "tech_count": ("Кол-во технологий", "разнообразие технологического стека"),
    "has_ai": ("Наличие ИИ", "использование технологий искусственного интеллекта"),
    "product_count": ("Кол-во продуктов", "число продуктов компании"),
    # Market (4)
    "industry_count": ("Отрасли", "число отраслей применения"),
    "project_count": ("Проекты", "число активных проектов"),
    "has_revenue": ("Наличие выручки", "компания уже зарабатывает"),
    "company_age": ("Возраст компании", "лет с момента основания"),
    # Categorical (6)
    "cluster_IT-кластер": ("Кластер: IT", "принадлежность к IT-кластеру"),
    "cluster_Биомед": ("Кластер: Биомед", "принадлежность к биомед-кластеру"),
    "cluster_Энерготех": ("Кластер: Энерготех", "принадлежность к энерготех-кластеру"),
    "cluster_Космос": ("Кластер: Космос", "принадлежность к космос-кластеру"),
    "cluster_Ядерные технологии": ("Кластер: Ядерные", "принадлежность к ядерному кластеру"),
    "status_encoded": ("Статус участника", "статус в Сколково"),
    # Text proxies (3)
    "len_company_desc": ("Полнота описания", "подробность описания компании"),
    "len_product_desc": ("Описание продуктов", "подробность описания продуктов"),
    "len_technologies": ("Описание технологий", "подробность описания технологий"),
}


def _format_shap_factor(feature: str, contribution: float) -> str:
    """Format a SHAP factor into human-readable Russian text."""
    label, hint = FEATURE_LABELS_RU.get(feature, (feature, ""))
    direction = "повышает оценку" if contribution > 0 else "снижает оценку"
    sign = "+" if contribution > 0 else ""
    icon = "✅" if contribution > 0 else "⚠️"
    return f"   {icon} {label} ({sign}{contribution:.2f}) — {direction}"

_predictor = None
_predictor_checked = False


def _get_predictor():
    """Lazy-load the predictor singleton."""
    global _predictor, _predictor_checked
    if _predictor_checked:
        return _predictor

    _predictor_checked = True
    try:
        from scoring.predictor import get_predictor
        p = get_predictor()
        if p.is_ready:
            _predictor = p
            logger.info(
                "ML scoring loaded (version=%s)", p.version
            )
        else:
            logger.info("ML scoring: models not found, using heuristics")
    except Exception as e:
        logger.warning("ML scoring unavailable: %s", e)

    return _predictor


def ml_analyze_startup(startup: dict) -> Optional[dict]:
    """
    Analyze a startup using the trained ML model.

    Returns a dict compatible with the old analyze_startup() format,
    enriched with ML scores. Returns None if ML is not available.
    """
    predictor = _get_predictor()
    if predictor is None:
        return None

    try:
        # Predict all 6 dimensions
        scores = predictor.predict(startup)
        overall = scores.get("overall", 0)
        tech = scores.get("tech_maturity", 0)
        innov = scores.get("innovation", 0)
        market = scores.get("market_potential", 0)
        team = scores.get("team_readiness", 0)
        financial = scores.get("financial_health", 0)

        # Map ML scores to the old format for backward compatibility
        # DeepTech: 1-3 based on tech_maturity
        if tech >= 7:
            deeptech = 3
        elif tech >= 4.5:
            deeptech = 2
        else:
            deeptech = 1

        # GenAI: check innovation + has_ai feature
        has_ai = any(
            kw in " ".join(
                str(startup.get(f, "")).lower()
                for f in ["company_description", "description",
                          "product_description", "technologies"]
            )
            for kw in ["ai", "ml", "искусственный интеллект",
                        "нейросеть", "машинное обучение", "нейронная сеть"]
        )
        genai = "есть" if (has_ai or innov >= 7) else "нет"

        # WOW
        wow = "да" if (deeptech == 3 and genai == "есть" and overall >= 7) else "нет"

        # TrafficLight: 1-3 based on overall score
        if overall >= 7:
            traffic_light = 3  # Green
        elif overall >= 4.5:
            traffic_light = 2  # Yellow
        else:
            traffic_light = 1  # Red

        # Build rich comments
        comments = []

        cluster = startup.get("cluster", "")
        if cluster:
            comments.append(f"📌 Кластер: {cluster}")

        status = startup.get("status", "")
        if status:
            comments.append(f"📊 Статус: {status}")

        technologies = startup.get("technologies", "")
        if technologies and len(technologies) > 10:
            tech_short = technologies[:100] + "..." if len(technologies) > 100 else technologies
            comments.append(f"🔧 Технологии: {tech_short}")

        # ML scores breakdown
        comments.append("")
        comments.append("🧠 ML-скоринг (6 измерений, XGBoost):")
        comments.append(f"   ⭐ Общий балл: {overall:.1f}/10")
        comments.append(f"   🔬 Технологическая зрелость: {tech:.1f}/10")
        comments.append(f"   💡 Инновационность: {innov:.1f}/10")
        comments.append(f"   📈 Рыночный потенциал: {market:.1f}/10")
        comments.append(f"   👥 Готовность команды: {team:.1f}/10")
        comments.append(f"   💰 Финансовое здоровье: {financial:.1f}/10")

        # SHAP explanation (top factors) with human-readable labels
        try:
            shap_result = predictor.explain(startup, target="overall", top_n=3)
            if shap_result:
                comments.append("")
                comments.append("📊 Ключевые факторы оценки:")
                for factor in shap_result.get("top_positive", [])[:3]:
                    comments.append(_format_shap_factor(
                        factor["feature"], factor["contribution"]
                    ))
                for factor in shap_result.get("top_negative", [])[:2]:
                    comments.append(_format_shap_factor(
                        factor["feature"], factor["contribution"]
                    ))
        except Exception:
            pass

        comment = "\n".join(comments)

        return {
            "DeepTech": deeptech,
            "GenAI": genai,
            "WOW": wow,
            "TrafficLight": traffic_light,
            "Comments": comment,
            "FinancialStability": "ML-оценка",
            "AvgProfit": 0,
            "FinancialHealth": f"{financial:.1f}/10",
            # New ML-specific fields
            "ml_scores": scores,
            "ml_available": True,
            "ml_overall": overall,
        }

    except Exception as e:
        logger.warning("ML scoring failed for %s: %s", startup.get("name", "?"), e)
        return None
