"""
Few-shot примеры для улучшения точности GigaChat
Статические примеры + динамические из истории
"""

# Статические примеры для разных типов запросов
FEW_SHOT_EXAMPLES = {
    "clean_tech": {
        "description": "Clean Tech, устойчивое развитие, экология",
        "examples": [
            {
                "query": "переработка пластика, устойчивое развитие",
                "relevant": [
                    "Компании по производству биоразлагаемых материалов",
                    "Стартапы по переработке полимерных отходов",
                    "Технологии вторичной переработки пластмасс"
                ],
                "not_relevant": [
                    "Общие IT-компании без экологического фокуса",
                    "Разработка мобильных приложений",
                    "Финансовые сервисы"
                ],
                "clusters": ["Энерготех", "Промтех"],
                "keywords": ["переработка", "экология", "отходы", "биоразлагаемый", "вторичное сырье"]
            },
            {
                "query": "водородная энергетика, альтернативные источники энергии",
                "relevant": [
                    "Производство водородных топливных элементов",
                    "Системы хранения водорода",
                    "Электролизеры для производства зеленого водорода"
                ],
                "not_relevant": [
                    "Традиционная энергетика (уголь, газ)",
                    "Программное обеспечение без связи с энергетикой",
                    "Переработка древесины"
                ],
                "clusters": ["Энерготех"],
                "keywords": ["водород", "топливные элементы", "электролиз", "зеленая энергия"]
            }
        ]
    },
    "ai_ml": {
        "description": "Искусственный интеллект, машинное обучение",
        "examples": [
            {
                "query": "компьютерное зрение, обработка изображений",
                "relevant": [
                    "Системы распознавания объектов",
                    "Медицинская диагностика на основе изображений",
                    "Автономные системы навигации"
                ],
                "not_relevant": [
                    "Обработка текстов (NLP) без компьютерного зрения",
                    "Традиционная фотография без AI",
                    "Производство камер"
                ],
                "clusters": ["ИТ", "Биомедицина"],
                "keywords": ["computer vision", "распознавание", "изображения", "нейросети", "детекция"]
            },
            {
                "query": "обработка естественного языка, NLP",
                "relevant": [
                    "Чат-боты и виртуальные ассистенты",
                    "Системы машинного перевода",
                    "Анализ тональности текстов"
                ],
                "not_relevant": [
                    "Компьютерное зрение без текстовой компоненты",
                    "Традиционные CRM без AI",
                    "Производство оборудования"
                ],
                "clusters": ["ИТ"],
                "keywords": ["nlp", "текст", "язык", "перевод", "чат-бот", "диалоговые системы"]
            }
        ]
    },
    "medtech": {
        "description": "Медицинские технологии, биотех",
        "examples": [
            {
                "query": "медицинская диагностика, AI в медицине",
                "relevant": [
                    "Системы диагностики на основе AI",
                    "Медицинские устройства с ML",
                    "Телемедицина с интеллектуальным анализом"
                ],
                "not_relevant": [
                    "AI без медицинского применения",
                    "Традиционное медицинское оборудование без AI",
                    "Фармацевтика без диагностического компонента"
                ],
                "clusters": ["Биомедицина"],
                "keywords": ["диагностика", "медицина", "здравоохранение", "пациент", "клинический"]
            }
        ]
    },
    "fintech": {
        "description": "Финансовые технологии",
        "examples": [
            {
                "query": "блокчейн, криптовалюты, DeFi",
                "relevant": [
                    "Платформы для криптовалютных транзакций",
                    "Децентрализованные финансовые сервисы",
                    "Блокчейн-решения для бизнеса"
                ],
                "not_relevant": [
                    "Традиционный банкинг без блокчейна",
                    "IT-решения без финансового компонента",
                    "Производство оборудования"
                ],
                "clusters": ["ИТ", "Финансовый сектор"],
                "keywords": ["блокчейн", "криптовалюта", "defi", "смарт-контракты", "токен"]
            }
        ]
    },
    "automotive": {
        "description": "Автомобильная промышленность, транспорт",
        "examples": [
            {
                "query": "автономные транспортные средства, беспилотники",
                "relevant": [
                    "Системы автономного вождения",
                    "Датчики и сенсоры для беспилотных авто",
                    "Программное обеспечение для ADAS"
                ],
                "not_relevant": [
                    "Дорожная инфраструктура без автономных систем",
                    "Традиционное автопроизводство без AI",
                    "Логистика без автономных компонентов"
                ],
                "clusters": ["Промтех", "ИТ"],
                "keywords": ["автономный", "беспилотный", "adas", "автомобиль", "транспорт", "навигация"]
            }
        ]
    }
}

def get_few_shot_prompt(query: str, history_patterns: list = None) -> str:
    """
    Генерация few-shot промпта на основе запроса
    
    Args:
        query: запрос пользователя
        history_patterns: паттерны из истории запросов
        
    Returns:
        Текст с примерами для промпта
    """
    query_lower = query.lower()
    
    # Определяем категорию запроса
    relevant_examples = []
    
    # 1. Проверяем АВТОМАТИЧЕСКИ ВЫУЧЕННЫЕ примеры (приоритет!)
    try:
        from ai_learning.learned_examples import LEARNED_EXAMPLES
        for category, data in LEARNED_EXAMPLES.items():
            # Проверяем ключевые слова
            if "keywords" in data:
                keywords = data.get("keywords", [])
                if any(kw in query_lower for kw in keywords):
                    if "examples" in data:
                        relevant_examples.extend(data["examples"])
    except ImportError:
        pass  # Файл еще не создан
    
    # 2. Проверяем статические примеры
    for category, data in FEW_SHOT_EXAMPLES.items():
        # Проверяем ключевые слова
        if any(keyword in query_lower for keyword in data.get("keywords", [])):
            relevant_examples.extend(data["examples"])
    
    # Добавляем примеры из истории
    if history_patterns:
        for pattern in history_patterns[:2]:  # Топ-2 из истории
            relevant_examples.append({
                "query": pattern.get("example_query", ""),
                "relevant": pattern.get("example_startups", "").split(", ")[:3],
                "clusters": pattern.get("relevant_clusters", "").split(", "),
                "keywords": pattern.get("keywords", "").split(", ")
            })
    
    if not relevant_examples:
        return ""
    
    # Формируем промпт
    prompt = "\n\nПРИМЕРЫ ИЗ ОПЫТА (Few-Shot Learning):\n\n"
    
    for i, example in enumerate(relevant_examples[:3], 1):  # Максимум 3 примера
        prompt += f"ПРИМЕР {i}:\n"
        prompt += f"Запрос: \"{example.get('query', '')}\"\n"
        
        if example.get('relevant'):
            prompt += "✅ Релевантные компании:\n"
            for company in example['relevant'][:3]:
                prompt += f"  • {company}\n"
        
        if example.get('not_relevant'):
            prompt += "❌ Нерелевантные компании:\n"
            for company in example['not_relevant'][:2]:
                prompt += f"  • {company}\n"
        
        if example.get('clusters'):
            prompt += f"Релевантные кластеры: {', '.join(example['clusters'])}\n"
        
        if example.get('keywords'):
            prompt += f"Ключевые слова: {', '.join(example['keywords'][:5])}\n"
        
        prompt += "\n"
    
    prompt += "Используй эти примеры для оценки текущего запроса.\n"
    prompt += "Обращай внимание на совпадения по ключевым словам, кластерам и технологиям.\n"
    
    return prompt

def detect_query_category(query: str) -> str:
    """Определение категории запроса"""
    query_lower = query.lower()
    
    # Проверяем каждую категорию
    for category, data in FEW_SHOT_EXAMPLES.items():
        # Проверяем ключевые слова из примеров
        for example in data.get("examples", []):
            keywords = example.get("keywords", [])
            if any(keyword in query_lower for keyword in keywords):
                return category
    
    return "general"

