"""
Утилиты для форматирования текста
"""
import re


def remove_emojis(text: str) -> str:
    """Удаляет смайлики из текста для экспорта в таблицы"""
    # Паттерн для удаления эмодзи
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # эмоции
        "\U0001F300-\U0001F5FF"  # символы и пиктограммы
        "\U0001F680-\U0001F6FF"  # транспорт и символы карт
        "\U0001F1E0-\U0001F1FF"  # флаги
        "\U00002702-\U000027B0"  # дингбаты
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # дополнительные символы
        "\U0001FA70-\U0001FAFF"  # расширенные символы
        "]+", 
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', text).strip()


def escape_html(text: str) -> str:
    """Экранирует HTML-символы для безопасной отправки в Telegram"""
    if not text:
        return text
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


