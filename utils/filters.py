"""
Утилиты для работы с фильтрами
"""
from typing import Any, Dict
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


async def get_filters(ud: Dict[str, Any]) -> dict:
    """Получить объединенные фильтры из состояния пользователя"""
    filters = ud.get("filters", {"criteria": {}, "additional": {}})
    merged_filters = {**filters["criteria"], **filters["additional"]}
    return merged_filters


def parse_criteria_text(text: str) -> dict:
    """Парсит текстовое представление критериев фильтрации"""
    criteria = {}
    parts = text.split()
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key == "DeepTech" and value in ["1", "2", "3"]:
                criteria[key] = value
            elif key == "GenAI" and value in ["есть", "нет"]:
                criteria[key] = value
            elif key == "WOW" and value in ["да", "нет"]:
                criteria[key] = value
    return criteria


def create_criteria_keyboard(selected_criteria: dict) -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора критериев фильтрации"""
    keyboard = []
    deeptech_row = []
    for i in range(1, 4):
        text = f"DeepTech={i}"
        if selected_criteria.get("DeepTech") == str(i):
            text = f"✅ {text}"
        deeptech_row.append(InlineKeyboardButton(text=text, callback_data=f"criteria_DeepTech_{i}"))
    keyboard.append(deeptech_row)

    genai_row = []
    for value in ["есть", "нет"]:
        text = f"GenAI={value}"
        if selected_criteria.get("GenAI") == value:
            text = f"✅ {text}"
        genai_row.append(InlineKeyboardButton(text=text, callback_data=f"criteria_GenAI_{value}"))
    keyboard.append(genai_row)

    wow_row = []
    for value in ["да", "нет"]:
        text = f"WOW={value}"
        if selected_criteria.get("WOW") == value:
            text = f"✅ {text}"
        wow_row.append(InlineKeyboardButton(text=text, callback_data=f"criteria_WOW_{value}"))
    keyboard.append(wow_row)

    keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="criteria_done")])
    return InlineKeyboardMarkup(inline_keyboard=[[btn for btn in row] for row in keyboard])

