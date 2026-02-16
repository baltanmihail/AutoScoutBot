"""
Модуль глубокого анализа стартапа

Функции:
- Анализ дополнительных данных из БД (рекомендации в ячейках TRL, IRL, MRL, CRL)
- Интеграция с внешними источниками (Checko.ru, РБК, официальные порталы)
- Агрегация и проверка достоверности информации
- Генерация расширенного отчета
"""
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DeepAnalysisService:
    """
    Сервис для глубокого анализа стартапа
    """
    
    def __init__(self):
        self.external_sources_enabled = False  # Пока отключено, будет включено после тестирования
    
    def analyze_startup_deep(
        self,
        startup: Dict,
        user_request: str = "",
        include_external: bool = False
    ) -> Dict:
        """
        Проводит глубокий анализ стартапа
        
        Args:
            startup: Данные стартапа из БД
            user_request: Исходный запрос пользователя
            include_external: Включать ли данные из внешних источников
        
        Returns:
            Словарь с результатами глубокого анализа
        """
        analysis = {
            "startup_name": startup.get("name", "н/д"),
            "inn": startup.get("inn", ""),
            "ogrn": startup.get("ogrn", ""),
            "timestamp": datetime.now().isoformat(),
            "internal_analysis": {},
            "external_analysis": {},
            "recommendations": [],
            "risk_factors": [],
            "opportunities": [],
        }
        
        # 1. Анализ внутренних данных (БД Сколково)
        analysis["internal_analysis"] = self._analyze_internal_data(startup)
        
        # 2. Анализ рекомендаций в ячейках TRL, IRL, MRL, CRL
        analysis["internal_analysis"]["level_recommendations"] = self._extract_level_recommendations(startup)
        
        # 3. Внешние источники (если включено)
        if include_external and self.external_sources_enabled:
            analysis["external_analysis"] = self._analyze_external_sources(
                startup.get("inn", ""),
                startup.get("ogrn", "")
            )
        
        # 4. Генерация рекомендаций
        analysis["recommendations"] = self._generate_recommendations(analysis)
        
        # 5. Выявление рисков
        analysis["risk_factors"] = self._identify_risks(analysis)
        
        # 6. Выявление возможностей
        analysis["opportunities"] = self._identify_opportunities(analysis, user_request)
        
        return analysis
    
    def _analyze_internal_data(self, startup: Dict) -> Dict:
        """Анализ внутренних данных из БД Сколково"""
        internal = {
            "financial_analysis": {},
            "technology_analysis": {},
            "market_analysis": {},
            "team_analysis": {},
        }
        
        # Финансовый анализ
        avg_profit = startup.get("avg_profit", 0)
        max_profit = startup.get("max_profit", 0)
        
        internal["financial_analysis"] = {
            "avg_profit": avg_profit,
            "max_profit": max_profit,
            "growth_trend": "растущий" if max_profit > avg_profit else "стабильный",
            "financial_health": self._assess_financial_health(avg_profit, max_profit),
        }
        
        # Технологический анализ
        trl = self._extract_level_value(startup.get("trl", 0))
        irl = self._extract_level_value(startup.get("irl", 0))
        mrl = self._extract_level_value(startup.get("mrl", 0))
        crl = self._extract_level_value(startup.get("crl", 0))
        
        internal["technology_analysis"] = {
            "trl": trl,
            "irl": irl,
            "mrl": mrl,
            "crl": crl,
            "average_level": (trl + irl + mrl + crl) / 4 if (trl + irl + mrl + crl) > 0 else 0,
            "readiness_assessment": self._assess_readiness(trl, irl, mrl, crl),
        }
        
        # Анализ рынка
        cluster = startup.get("cluster", "")
        category = startup.get("category", "")
        status = startup.get("status", "")
        
        internal["market_analysis"] = {
            "cluster": cluster,
            "category": category,
            "status": status,
            "market_position": self._assess_market_position(cluster, status),
        }
        
        # Анализ команды
        internal["team_analysis"] = {
            "crl": crl,
            "team_readiness": self._assess_team_readiness(crl),
        }
        
        return internal
    
    def _extract_level_recommendations(self, startup: Dict) -> Dict:
        """
        Извлекает рекомендации из ячеек с уровнями зрелости
        
        В БД могут быть текстовые рекомендации в полях trl, irl, mrl, crl
        помимо числовых значений
        """
        recommendations = {
            "trl": [],
            "irl": [],
            "mrl": [],
            "crl": [],
        }
        
        # Пытаемся извлечь текстовые рекомендации
        for level in ["trl", "irl", "mrl", "crl"]:
            value = startup.get(level, "")
            
            if isinstance(value, str):
                # Ищем паттерны типа "5 (рекомендация: ...)" или просто текст
                match = re.search(r'рекомендация[:\s]+(.+?)(?:\n|$)', value, re.IGNORECASE)
                if match:
                    recommendations[level].append(match.group(1).strip())
                
                # Ищем паттерны типа "5 - описание"
                match = re.search(r'\d+\s*[-–]\s*(.+?)(?:\n|$)', value)
                if match:
                    recommendations[level].append(match.group(1).strip())
        
        return recommendations
    
    def _analyze_external_sources(
        self,
        inn: str,
        ogrn: str
    ) -> Dict:
        """
        Анализ данных из внешних источников
        
        TODO: Реализовать интеграцию с:
        - Checko.ru (БФО)
        - Официальные порталы (ФНС, ЕГРЮЛ)
        - РБК, Коммерсант и другие СМИ
        - Другие базы стартапов
        
        Args:
            inn: ИНН компании
            ogrn: ОГРН компании
        
        Returns:
            Словарь с данными из внешних источников
        """
        external = {
            "financial_data": {},
            "news_mentions": [],
            "reliability_score": 0.0,
            "sources": [],
        }
        
        if not inn and not ogrn:
            logger.warning("Нет ИНН/ОГРН для внешнего анализа")
            return external
        
        # TODO: Реализовать парсинг внешних источников
        # См. test_external_sources.py для примеров
        
        return external
    
    def _assess_financial_health(self, avg_profit: float, max_profit: float) -> str:
        """Оценка финансового здоровья"""
        if avg_profit <= 0:
            return "критическое"
        elif avg_profit < 1_000_000:
            return "слабое"
        elif avg_profit < 10_000_000:
            return "умеренное"
        elif max_profit > avg_profit * 1.5:
            return "отличное (растущее)"
        else:
            return "стабильное"
    
    def _assess_readiness(self, trl: int, irl: int, mrl: int, crl: int) -> str:
        """Оценка общей готовности проекта"""
        avg = (trl + irl + mrl + crl) / 4 if (trl + irl + mrl + crl) > 0 else 0
        
        if avg >= 7:
            return "высокая готовность к коммерциализации"
        elif avg >= 5:
            return "средняя готовность, требуется доработка"
        elif avg >= 3:
            return "низкая готовность, ранняя стадия"
        else:
            return "очень ранняя стадия, концепция"
    
    def _assess_market_position(self, cluster: str, status: str) -> str:
        """Оценка позиции на рынке"""
        if status == "active":
            return "активная деятельность"
        elif status == "inactive":
            return "неактивная деятельность"
        else:
            return "статус не определен"
    
    def _assess_team_readiness(self, crl: int) -> str:
        """Оценка готовности команды"""
        if crl >= 7:
            return "высокая готовность команды"
        elif crl >= 5:
            return "средняя готовность команды"
        elif crl >= 3:
            return "базовая готовность команды"
        else:
            return "команда формируется"
    
    def _generate_recommendations(self, analysis: Dict) -> List[str]:
        """Генерация рекомендаций на основе анализа"""
        recommendations = []
        
        internal = analysis.get("internal_analysis", {})
        tech = internal.get("technology_analysis", {})
        finance = internal.get("financial_analysis", {})
        
        # Рекомендации по технологиям
        avg_level = tech.get("average_level", 0)
        if avg_level < 5:
            recommendations.append(
                "Проект находится на ранней стадии. Рекомендуется дополнительная "
                "проработка технологической зрелости перед масштабированием."
            )
        
        # Рекомендации по финансам
        financial_health = finance.get("financial_health", "")
        if "критическое" in financial_health or "слабое" in financial_health:
            recommendations.append(
                "Финансовое положение требует внимания. Рекомендуется привлечение "
                "дополнительного финансирования или оптимизация расходов."
            )
        
        # Рекомендации из ячеек уровней
        level_recs = internal.get("level_recommendations", {})
        for level, recs in level_recs.items():
            if recs:
                recommendations.extend(recs)
        
        return recommendations
    
    def _identify_risks(self, analysis: Dict) -> List[str]:
        """Выявление рисков"""
        risks = []
        
        internal = analysis.get("internal_analysis", {})
        tech = internal.get("technology_analysis", {})
        finance = internal.get("financial_analysis", {})
        
        # Технологические риски
        if tech.get("trl", 0) < 3:
            risks.append("Низкий уровень технологической зрелости (TRL < 3)")
        
        # Финансовые риски
        if finance.get("avg_profit", 0) <= 0:
            risks.append("Отсутствие подтвержденной прибыли")
        
        # Риски команды
        if internal.get("team_analysis", {}).get("crl", 0) < 3:
            risks.append("Слабая готовность команды (CRL < 3)")
        
        return risks
    
    def _identify_opportunities(self, analysis: Dict, user_request: str) -> List[str]:
        """Выявление возможностей"""
        opportunities = []
        
        internal = analysis.get("internal_analysis", {})
        tech = internal.get("technology_analysis", {})
        
        # Возможности по технологиям
        if tech.get("trl", 0) >= 7:
            opportunities.append("Высокая технологическая зрелость - готовность к масштабированию")
        
        if tech.get("irl", 0) >= 6:
            opportunities.append("Интерес инвесторов подтвержден (IRL ≥ 6)")
        
        # Возможности по запросу пользователя
        if user_request:
            opportunities.append(
                f"Проект соответствует запросу '{user_request[:50]}...' "
                "и может быть интересен для дальнейшего изучения."
            )
        
        return opportunities
    
    def _extract_level_value(self, value) -> int:
        """Извлекает числовое значение уровня из строки или числа"""
        if isinstance(value, int):
            return value
        elif isinstance(value, str):
            # Ищем первое число в строке
            match = re.search(r'\d+', value)
            if match:
                return int(match.group())
        return 0
    
    def format_deep_analysis_report(self, analysis: Dict) -> str:
        """
        Форматирует отчет глубокого анализа для вывода в Telegram
        
        Args:
            analysis: Результат analyze_startup_deep
        
        Returns:
            Отформатированный текст отчета
        """
        report = f"🔬 <b>ГЛУБОКИЙ АНАЛИЗ: {analysis['startup_name']}</b>\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Внутренний анализ
        internal = analysis.get("internal_analysis", {})
        
        # Технологии
        tech = internal.get("technology_analysis", {})
        report += f"<b>🔬 Технологическая зрелость:</b>\n"
        report += f"• TRL: {tech.get('trl', 0)}/9\n"
        report += f"• IRL: {tech.get('irl', 0)}/9\n"
        report += f"• MRL: {tech.get('mrl', 0)}/9\n"
        report += f"• CRL: {tech.get('crl', 0)}/9\n"
        report += f"• Средний уровень: {tech.get('average_level', 0):.1f}\n"
        report += f"• Оценка: {tech.get('readiness_assessment', 'н/д')}\n\n"
        
        # Финансы
        finance = internal.get("financial_analysis", {})
        report += f"<b>💰 Финансовый анализ:</b>\n"
        report += f"• Средняя прибыль: {finance.get('avg_profit', 0) / 1_000_000:.2f} млн руб\n"
        report += f"• Максимальная прибыль: {finance.get('max_profit', 0) / 1_000_000:.2f} млн руб\n"
        report += f"• Тренд: {finance.get('growth_trend', 'н/д')}\n"
        report += f"• Оценка: {finance.get('financial_health', 'н/д')}\n\n"
        
        # Рекомендации
        recommendations = analysis.get("recommendations", [])
        if recommendations:
            report += f"<b>💡 Рекомендации:</b>\n"
            for i, rec in enumerate(recommendations[:5], 1):  # Максимум 5
                report += f"{i}. {rec}\n"
            report += "\n"
        
        # Риски
        risks = analysis.get("risk_factors", [])
        if risks:
            report += f"<b>⚠️ Риски:</b>\n"
            for i, risk in enumerate(risks[:5], 1):  # Максимум 5
                report += f"{i}. {risk}\n"
            report += "\n"
        
        # Возможности
        opportunities = analysis.get("opportunities", [])
        if opportunities:
            report += f"<b>🚀 Возможности:</b>\n"
            for i, opp in enumerate(opportunities[:5], 1):  # Максимум 5
                report += f"{i}. {opp}\n"
            report += "\n"
        
        # Внешние источники (если есть)
        external = analysis.get("external_analysis", {})
        if external.get("sources"):
            report += f"<b>📰 Внешние источники:</b>\n"
            report += f"• Найдено источников: {len(external.get('sources', []))}\n"
            report += f"• Достоверность: {external.get('reliability_score', 0):.1%}\n\n"
        
        report += f"<i>Полный отчет доступен в файле Excel/CSV</i>"
        
        return report

