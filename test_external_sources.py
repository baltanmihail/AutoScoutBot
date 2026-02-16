"""
Тестовый файл для экспериментов с интеграцией внешних источников

Планируемые источники:
1. Checko.ru - БФО (бухгалтерская финансовая отчетность)
2. Официальные порталы (ФНС, ЕГРЮЛ)
3. РБК, Коммерсант и другие СМИ
4. Другие базы стартапов (Crunchbase, PitchBook и т.д.)

Логика проверки достоверности:
- Чем чаще информация повторяется в разных источниках, тем она надежнее
- Авторитетные источники имеют больший вес
- Проверка на противоречия между источниками
"""
import logging
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ExternalSource:
    """Метаданные внешнего источника"""
    name: str
    url: str
    authority_score: float  # 0.0 - 1.0 (насколько авторитетен источник)
    requires_auth: bool
    rate_limit: Optional[int] = None  # Запросов в минуту


class ExternalSourcesService:
    """
    Сервис для работы с внешними источниками данных
    
    TODO: Реализовать интеграции с различными источниками
    """
    
    def __init__(self):
        self.sources = self._initialize_sources()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def _initialize_sources(self) -> List[ExternalSource]:
        """Инициализация списка источников"""
        sources = [
            # Официальные источники (высокий авторитет)
            ExternalSource(
                name="ЕГРЮЛ (ФНС)",
                url="https://egrul.nalog.ru/",
                authority_score=1.0,
                requires_auth=False,
            ),
            ExternalSource(
                name="ФНС - Проверка контрагента",
                url="https://service.nalog.ru/",
                authority_score=1.0,
                requires_auth=False,
            ),
            
            # Коммерческие источники (средний авторитет)
            ExternalSource(
                name="Checko.ru",
                url="https://checko.ru/",
                authority_score=0.8,
                requires_auth=False,
                rate_limit=10,  # Примерное ограничение
            ),
            ExternalSource(
                name="СПАРК Интерфакс",
                url="https://www.spark-interfax.ru/",
                authority_score=0.9,
                requires_auth=True,  # Требует API ключ
            ),
            
            # СМИ (низкий-средний авторитет для финансовых данных)
            ExternalSource(
                name="РБК",
                url="https://www.rbc.ru/",
                authority_score=0.6,
                requires_auth=False,
            ),
            ExternalSource(
                name="Коммерсант",
                url="https://www.kommersant.ru/",
                authority_score=0.7,
                requires_auth=False,
            ),
            
            # Базы стартапов (средний авторитет)
            ExternalSource(
                name="Crunchbase",
                url="https://www.crunchbase.com/",
                authority_score=0.7,
                requires_auth=True,  # Требует API ключ
            ),
        ]
        
        return sources
    
    def search_by_inn(self, inn: str) -> Dict:
        """
        Поиск информации по ИНН
        
        Args:
            inn: ИНН компании
        
        Returns:
            Словарь с агрегированными данными из всех источников
        """
        results = {
            "inn": inn,
            "sources_checked": [],
            "financial_data": {},
            "news_mentions": [],
            "reliability_score": 0.0,
            "contradictions": [],
        }
        
        # TODO: Реализовать парсинг каждого источника
        # Пока заглушка
        
        logger.info(f"🔍 Поиск по ИНН: {inn}")
        
        # Пример: Checko.ru (требует парсинг HTML или API)
        # checko_data = self._parse_checko(inn)
        # if checko_data:
        #     results["sources_checked"].append("Checko.ru")
        #     results["financial_data"].update(checko_data)
        
        # Пример: ЕГРЮЛ (официальный источник)
        # egryl_data = self._parse_egryl(inn)
        # if egryl_data:
        #     results["sources_checked"].append("ЕГРЮЛ")
        #     results["financial_data"].update(egryl_data)
        
        # Пример: РБК (поиск новостей)
        # rbc_news = self._search_rbc_news(inn)
        # if rbc_news:
        #     results["sources_checked"].append("РБК")
        #     results["news_mentions"].extend(rbc_news)
        
        # Вычисляем reliability_score на основе количества источников
        results["reliability_score"] = self._calculate_reliability(results)
        
        return results
    
    def _parse_checko(self, inn: str) -> Optional[Dict]:
        """
        Парсинг данных с Checko.ru
        
        TODO: Реализовать
        - Вариант 1: Парсинг HTML (selenium/beautifulsoup)
        - Вариант 2: API (если доступно)
        """
        try:
            # Пример URL: https://checko.ru/company/inn
            url = f"https://checko.ru/company/{inn}"
            
            # TODO: Реализовать парсинг
            # response = self.session.get(url, timeout=10)
            # if response.status_code == 200:
            #     # Парсим HTML
            #     # Извлекаем БФО, финансовые показатели и т.д.
            #     pass
            
            logger.info(f"⚠️ Парсинг Checko.ru не реализован (ИНН: {inn})")
            return None
        
        except Exception as e:
            logger.error(f"Ошибка парсинга Checko.ru: {e}")
            return None
    
    def _parse_egryl(self, inn: str) -> Optional[Dict]:
        """
        Парсинг данных из ЕГРЮЛ (официальный источник)
        
        TODO: Реализовать через официальный API или парсинг
        """
        try:
            # ЕГРЮЛ предоставляет официальный API
            # URL: https://egrul.nalog.ru/
            
            # TODO: Реализовать
            logger.info(f"⚠️ Парсинг ЕГРЮЛ не реализован (ИНН: {inn})")
            return None
        
        except Exception as e:
            logger.error(f"Ошибка парсинга ЕГРЮЛ: {e}")
            return None
    
    def _search_rbc_news(self, inn: str) -> List[Dict]:
        """
        Поиск упоминаний компании в новостях РБК
        
        TODO: Реализовать через поиск РБК или RSS
        """
        try:
            # РБК имеет поиск по сайту
            # Можно использовать поисковый запрос с ИНН или названием компании
            
            # TODO: Реализовать
            logger.info(f"⚠️ Поиск в РБК не реализован (ИНН: {inn})")
            return []
        
        except Exception as e:
            logger.error(f"Ошибка поиска в РБК: {e}")
            return []
    
    def _calculate_reliability(self, results: Dict) -> float:
        """
        Вычисляет оценку достоверности информации
        
        Логика:
        - Чем больше источников подтверждают информацию, тем выше достоверность
        - Авторитетные источники имеют больший вес
        - Противоречия снижают достоверность
        """
        sources_checked = results.get("sources_checked", [])
        
        if not sources_checked:
            return 0.0
        
        # Находим источники в нашем списке
        checked_sources = [
            s for s in self.sources
            if s.name in sources_checked
        ]
        
        if not checked_sources:
            return 0.0
        
        # Средний authority_score проверенных источников
        avg_authority = sum(s.authority_score for s in checked_sources) / len(checked_sources)
        
        # Множитель за количество источников (чем больше, тем лучше)
        source_count_multiplier = min(len(sources_checked) / 3, 1.0)  # Максимум при 3+ источниках
        
        # Учитываем противоречия
        contradictions = results.get("contradictions", [])
        contradiction_penalty = len(contradictions) * 0.1
        
        reliability = avg_authority * source_count_multiplier - contradiction_penalty
        
        return max(0.0, min(1.0, reliability))  # Ограничиваем 0.0 - 1.0
    
    def aggregate_financial_data(self, results: Dict) -> Dict:
        """
        Агрегирует финансовые данные из разных источников
        
        Логика:
        - Если данные совпадают в нескольких источниках → высокая достоверность
        - Если данные различаются → берем среднее или медиану
        - Приоритет официальным источникам
        """
        aggregated = {
            "revenue": None,
            "profit": None,
            "assets": None,
            "liabilities": None,
            "reliability": 0.0,
        }
        
        # TODO: Реализовать агрегацию
        # Собираем данные из всех источников
        # Сравниваем значения
        # Вычисляем среднее/медиану
        # Присваиваем reliability на основе совпадений
        
        return aggregated


# ============================================================================
# ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ
# ============================================================================

def test_external_sources():
    """Тестовая функция для проверки работы с внешними источниками"""
    
    service = ExternalSourcesService()
    
    # Тестовый ИНН (замените на реальный)
    test_inn = "7731383390"  # Пример из базы
    
    print("=" * 60)
    print("ТЕСТ: Поиск по внешним источникам")
    print("=" * 60)
    
    results = service.search_by_inn(test_inn)
    
    print(f"\nИНН: {results['inn']}")
    print(f"Проверено источников: {len(results['sources_checked'])}")
    print(f"Достоверность: {results['reliability_score']:.1%}")
    
    if results['sources_checked']:
        print(f"\nИсточники:")
        for source in results['sources_checked']:
            print(f"  • {source}")
    else:
        print("\n⚠️ Источники не проверены (функции не реализованы)")
    
    print("\n" + "=" * 60)
    print("СЛЕДУЮЩИЕ ШАГИ:")
    print("=" * 60)
    print("1. Реализовать парсинг Checko.ru (HTML или API)")
    print("2. Реализовать парсинг ЕГРЮЛ (официальный API)")
    print("3. Реализовать поиск в новостях (РБК, Коммерсант)")
    print("4. Добавить агрегацию данных")
    print("5. Добавить проверку на противоречия")
    print("6. Интегрировать в services/deep_analysis.py")


if __name__ == "__main__":
    test_external_sources()

