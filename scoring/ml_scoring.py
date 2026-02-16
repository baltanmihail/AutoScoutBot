"""
ML Scoring bridge -- connects trained LightGBM models to the bot.

Usage in bot code:
    from scoring.ml_scoring import ml_analyze_startup
    result = ml_analyze_startup(startup_dict)
    # -> {"DeepTech": 3, "GenAI": "есть", "WOW": "да", "TrafficLight": 3,
    #     "Comments": "...", "ml_scores": {...}, "ml_available": True}

Falls back gracefully if models are not trained yet.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

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
        comments.append(f"🧠 ML-оценка (LightGBM, обучена на данных Сколково):")
        comments.append(f"   ⭐ Общий балл: {overall:.1f}/10")
        comments.append(f"   🔬 Технологическая зрелость: {tech:.1f}/10")
        comments.append(f"   💡 Инновационность: {innov:.1f}/10")
        comments.append(f"   📈 Рыночный потенциал: {market:.1f}/10")
        comments.append(f"   👥 Готовность команды: {team:.1f}/10")
        comments.append(f"   💰 Финансовое здоровье: {financial:.1f}/10")

        # SHAP explanation (top factors)
        try:
            shap_result = predictor.explain(startup, target="overall", top_n=3)
            if shap_result:
                comments.append("")
                comments.append("📊 Ключевые факторы оценки:")
                for factor in shap_result.get("top_positive", [])[:3]:
                    feat = factor["feature"]
                    contrib = factor["contribution"]
                    comments.append(f"   ✅ {feat}: +{contrib:.2f}")
                for factor in shap_result.get("top_negative", [])[:2]:
                    feat = factor["feature"]
                    contrib = factor["contribution"]
                    comments.append(f"   ⚠️ {feat}: {contrib:.2f}")
        except Exception:
            pass

        # Traffic light label
        traffic_light_map = {
            1: "🔴 Красный (низкий потенциал)",
            2: "🟡 Желтый (средний потенциал)",
            3: "🟢 Зеленый (высокий потенциал)",
        }
        comments.append("")
        comments.append(f"🚦 Итоговая оценка: {traffic_light_map[traffic_light]}")

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
