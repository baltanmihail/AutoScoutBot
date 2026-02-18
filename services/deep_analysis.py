"""
Модуль глубокого анализа стартапа

Функции:
- Анализ дополнительных данных из БД (рекомендации в ячейках TRL, IRL, MRL, CRL)
- Интеграция с внешними источниками (BFO, EGRUL, MOEX, News, Checko)
- Агрегация и проверка достоверности информации
- Генерация расширенного отчета
- Smart article search (query generation via GigaChat _internal)
"""
import asyncio
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
        self.external_sources_enabled = True  # Enabled: uses parsers from parsers/
    
    def analyze_startup_deep(
        self,
        startup: Dict,
        user_request: str = "",
        include_external: bool = False,
    ) -> Dict:
        """
        Synchronous deep analysis (backward compatible).
        For async with external sources, use analyze_startup_deep_async().
        """
        analysis = self._build_base_analysis(startup)

        # Internal analysis (always)
        analysis["internal_analysis"] = self._analyze_internal_data(startup)
        analysis["internal_analysis"]["level_recommendations"] = self._extract_level_recommendations(startup)

        # External sources (sync wrapper)
        if include_external and self.external_sources_enabled:
            analysis["external_analysis"] = self._analyze_external_sources(
                startup.get("inn", ""),
                startup.get("ogrn", ""),
            )

        analysis["recommendations"] = self._generate_recommendations(analysis)
        analysis["risk_factors"] = self._identify_risks(analysis)
        analysis["opportunities"] = self._identify_opportunities(analysis, user_request)

        return analysis

    async def analyze_startup_deep_async(
        self,
        startup: Dict,
        user_request: str = "",
        include_external: bool = True,
    ) -> Dict:
        """
        Full async deep analysis with external sources and smart article search.
        """
        analysis = self._build_base_analysis(startup)

        # 1. Internal analysis
        analysis["internal_analysis"] = self._analyze_internal_data(startup)
        analysis["internal_analysis"]["level_recommendations"] = self._extract_level_recommendations(startup)

        inn = str(startup.get("inn", "")).strip()
        company_name = startup.get("name", "")

        # 2. External sources + smart article search (in parallel)
        if include_external and self.external_sources_enabled and inn:
            ext_task = self.analyze_external_sources(
                inn=inn,
                ogrn=str(startup.get("ogrn", "")),
                company_name=company_name,
            )
            articles_task = self.smart_article_search(
                company_name=company_name,
                context=f"{startup.get('cluster', '')} {startup.get('technologies', '')[:200]}",
            )
            ext_result, articles = await asyncio.gather(ext_task, articles_task)
            analysis["external_analysis"] = ext_result
            analysis["smart_articles"] = articles

        # 3. Recommendations, risks, opportunities
        analysis["recommendations"] = self._generate_recommendations(analysis)
        analysis["risk_factors"] = self._identify_risks(analysis)
        analysis["opportunities"] = self._identify_opportunities(analysis, user_request)

        return analysis

    @staticmethod
    def _build_base_analysis(startup: Dict) -> Dict:
        return {
            "startup_name": startup.get("name", "н/д"),
            "inn": startup.get("inn", ""),
            "ogrn": startup.get("ogrn", ""),
            "timestamp": datetime.now().isoformat(),
            "internal_analysis": {},
            "external_analysis": {},
            "smart_articles": [],
            "recommendations": [],
            "risk_factors": [],
            "opportunities": [],
        }
    
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
    
    async def analyze_external_sources(
        self,
        inn: str,
        ogrn: str = "",
        company_name: str = "",
    ) -> Dict:
        """
        Fetch and analyze data from external sources (BFO, EGRUL, MOEX, news, Checko).

        Args:
            inn: ИНН компании
            ogrn: ОГРН компании
            company_name: Название компании (для поиска в новостях)

        Returns:
            Dict with financial_data, legal_status, news_mentions, market_data, sources.
        """
        external = {
            "financial_data": {},
            "legal_status": {},
            "news_mentions": [],
            "market_data": {},
            "reliability_score": 0.0,
            "sources": [],
        }

        if not inn:
            logger.warning("Нет ИНН для внешнего анализа")
            return external

        try:
            from parsers.manager import ParserManager

            mgr = ParserManager()
            raw = await mgr.fetch_all(inn=inn, company_name=company_name)
            await mgr.close()

            # BFO -- financial data
            bfo = raw.get("bfo", {})
            if bfo:
                external["financial_data"] = bfo.get("financials", {})
                external["sources"].append({"name": "БФО ФНС", "key": "bfo"})

            # EGRUL -- legal status
            egrul = raw.get("egrul", {})
            if egrul:
                external["legal_status"] = {
                    "name": egrul.get("name", ""),
                    "ogrn": egrul.get("ogrn", ""),
                    "status": egrul.get("status", ""),
                    "is_active": egrul.get("is_active", None),
                    "registration_date": egrul.get("registration_date", ""),
                    "address": egrul.get("address", ""),
                }
                external["sources"].append({"name": "ЕГРЮЛ", "key": "egrul"})

            # MOEX -- market data
            moex = raw.get("moex", {})
            if moex and moex.get("has_quotes"):
                external["market_data"] = moex
                external["sources"].append({"name": "MOEX", "key": "moex"})

            # News -- mentions
            news = raw.get("news", {})
            if news and news.get("total_count", 0) > 0:
                external["news_mentions"] = news.get("mentions", [])
                external["sources"].append({"name": "СМИ (РБК/ТАСС/Интерфакс)", "key": "news"})

            # Checko -- aggregated financial summary
            checko = raw.get("checko", {})
            if checko:
                external["checko_summary"] = checko
                external["sources"].append({"name": "Checko.ru", "key": "checko"})

            # Reliability score (placeholder; real computation via ReliabilityEngine)
            external["reliability_score"] = len(external["sources"]) / 5.0

        except Exception as e:
            logger.error(f"Ошибка анализа внешних источников: {e}")

        return external

    # Keep old sync method name for backward compat (wraps async)
    def _analyze_external_sources(self, inn: str, ogrn: str) -> Dict:
        """Sync wrapper around async analyze_external_sources."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(
                        asyncio.run,
                        self.analyze_external_sources(inn, ogrn)
                    ).result(timeout=60)
            return asyncio.run(self.analyze_external_sources(inn, ogrn))
        except Exception as e:
            logger.warning(f"Sync external analysis failed: {e}")
            return {"financial_data": {}, "news_mentions": [], "reliability_score": 0.0, "sources": []}
    
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
    
    async def smart_article_search(self, company_name: str, context: str = "") -> List[Dict]:
        """
        Use GigaChat (_internal tier) to generate smart search queries,
        then search RSS feeds for relevant articles.

        GigaChat тратит остаточные токены -- не NeuroAPI.
        """
        articles: List[Dict] = []

        try:
            from config import GIGACHAT_API_TOKEN
            from gigachat import GigaChat
            from gigachat.models import Chat, Messages, MessagesRole

            if not GIGACHAT_API_TOKEN:
                logger.warning("smart_article_search: GIGACHAT_API_TOKEN not set")
                return articles

            giga = GigaChat(
                credentials=GIGACHAT_API_TOKEN,
                verify_ssl_certs=False,
                timeout=30,
                scope="GIGACHAT_API_PERS",
            )

            prompt = (
                f"Сгенерируй 3 поисковых запроса для поиска статей про компанию '{company_name}'. "
                f"Контекст: {context[:200]}. "
                "Ответь JSON-массивом строк, без markdown."
            )

            resp = giga.chat(Chat(
                messages=[Messages(role=MessagesRole.USER, content=prompt)],
                max_tokens=200,
                temperature=0.3,
            ))

            queries_text = resp.choices[0].message.content.strip() if resp.choices else "[]"
            queries_text = queries_text.replace("```json", "").replace("```", "").strip()

            import json
            try:
                queries = json.loads(queries_text)
            except json.JSONDecodeError:
                queries = [company_name]

            from parsers.news_parser import NewsParser
            parser = NewsParser()
            for query in queries[:3]:
                result = await parser.safe_fetch(inn="", company_name=str(query))
                for mention in result.get("mentions", []):
                    articles.append(mention)
            await parser.close()

            seen_links = set()
            unique = []
            for art in articles:
                link = art.get("link", "")
                if link and link not in seen_links:
                    seen_links.add(link)
                    unique.append(art)
            articles = unique[:10]

            if articles:
                titles = "\n".join(f"- {a['title']}" for a in articles[:5])
                summary_prompt = (
                    f"Кратко обобщи упоминания компании '{company_name}' в прессе "
                    f"на основе заголовков:\n{titles}\n\n"
                    "Ответь 2-3 предложениями на русском."
                )
                summary_resp = giga.chat(Chat(
                    messages=[Messages(role=MessagesRole.USER, content=summary_prompt)],
                    max_tokens=200,
                    temperature=0.4,
                ))
                if summary_resp.choices:
                    articles.insert(0, {
                        "source": "AI",
                        "title": "Сводка по СМИ",
                        "link": "",
                        "summary": summary_resp.choices[0].message.content.strip(),
                    })

        except Exception as e:
            logger.warning("smart_article_search error: %s", e)

        return articles

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
        
        # External sources
        external = analysis.get("external_analysis", {})
        sources = external.get("sources", [])
        if sources:
            report += "<b>🌐 Внешние источники:</b>\n"
            for src in sources:
                report += f"  • {src.get('name', src.get('key', ''))}\n"
            report += f"  Достоверность данных: {external.get('reliability_score', 0):.0%}\n\n"

        # Financial data from external
        fin = external.get("financial_data", {})
        if fin:
            report += "<b>💰 Финансы (внешние источники):</b>\n"
            for year in sorted(fin.keys(), reverse=True)[:3]:
                yd = fin[year] if isinstance(fin[year], dict) else {}
                rev = yd.get("revenue", 0)
                profit = yd.get("net_profit", 0)
                rev_s = f"{rev / 1_000_000:.1f} млн" if rev else "н/д"
                prof_s = f"{profit / 1_000_000:.1f} млн" if profit else "н/д"
                report += f"  • {year}: выручка {rev_s}, прибыль {prof_s}\n"
            report += "\n"

        # Legal status from EGRUL
        legal = external.get("legal_status", {})
        if legal:
            report += "<b>📋 Юридический статус (ЕГРЮЛ):</b>\n"
            if legal.get("status"):
                report += f"  • Статус: {legal['status']}\n"
            if legal.get("registration_date"):
                report += f"  • Дата рег.: {legal['registration_date']}\n"
            report += "\n"

        # News mentions
        news = external.get("news_mentions", [])
        if news:
            report += f"<b>📰 Упоминания в СМИ ({len(news)}):</b>\n"
            for mention in news[:5]:
                if mention.get("summary"):
                    report += f"  {mention['summary']}\n"
                else:
                    src = mention.get("source", "").upper()
                    title = mention.get("title", "")[:80]
                    report += f"  • [{src}] {title}\n"
            report += "\n"

        # Smart article search results
        smart_articles = analysis.get("smart_articles", [])
        if smart_articles:
            report += "<b>🔎 Найденные статьи (AI-поиск):</b>\n"
            for art in smart_articles[:5]:
                if art.get("summary"):
                    report += f"  📝 {art['summary']}\n"
                else:
                    report += f"  • [{art.get('source', '').upper()}] {art.get('title', '')[:80]}\n"
            report += "\n"

        report += "<i>Полный отчет доступен в файле Excel/CSV</i>"

        return report

