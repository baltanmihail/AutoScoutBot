"""
Модуль интерактивных действий после вывода результатов поиска

Функции:
1. Повторный поиск по тому же запросу
2. Уточнение запроса
3. Глубокий анализ стартапа
"""
import logging
from typing import Dict, List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)


def create_results_actions_keyboard(
    user_request: str,
    startup_ids: List[str],
    query_id: Optional[int] = None
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с интерактивными действиями после вывода результатов
    
    Args:
        user_request: Исходный запрос пользователя
        startup_ids: Список ID найденных стартапов
        query_id: ID запроса в истории (опционально)
    
    Returns:
        InlineKeyboardMarkup с кнопками действий
    """
    keyboard_buttons = []
    
    # 1. Повторный поиск по тому же запросу
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="🔄 Новая выборка по запросу",
            callback_data=f"action_rerun_{query_id or 'none'}"
        )
    ])
    
    # 2. Уточнить запрос
    keyboard_buttons.append([
        InlineKeyboardButton(
            text="✏️ Уточнить запрос",
            callback_data=f"action_refine_{query_id or 'none'}"
        )
    ])
    
    # 3. Глубокий анализ (для каждого стартапа)
    if startup_ids:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text="🔬 Глубокий анализ стартапа",
                callback_data="action_deep_analysis_menu"
            )
        ])
    
    # Кнопки экспорта убраны - они будут в отдельном сообщении
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


def create_export_keyboard() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопками экспорта
    
    Returns:
        InlineKeyboardMarkup с кнопками экспорта
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📤 Excel (xlsx)", callback_data="format_excel"),
                InlineKeyboardButton(text="📤 CSV", callback_data="format_csv"),
            ]
        ]
    )


def create_deep_analysis_keyboard(startup_ids: List[str], startup_names: List[str]) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора стартапа для глубокого анализа
    
    Args:
        startup_ids: Список ID стартапов
        startup_names: Список названий стартапов
    
    Returns:
        InlineKeyboardMarkup с кнопками выбора стартапа
    """
    keyboard_buttons = []
    
    for i, (startup_id, name) in enumerate(zip(startup_ids, startup_names), 1):
        # Ограничиваем длину названия для кнопки
        short_name = name[:30] + "..." if len(name) > 30 else name
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"{i}. {short_name}",
                callback_data=f"deep_analysis_{startup_id}"
            )
        ])
    
    # Кнопка "Назад"
    keyboard_buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="action_back_to_results")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


async def create_model_selection_keyboard(
    user_id: int,
    user_repository,
    action_type: str,
    action_data: str
) -> Optional[InlineKeyboardMarkup]:
    """
    Создает клавиатуру выбора модели для интерактивного действия
    
    Args:
        user_id: ID пользователя
        user_repository: Репозиторий пользователей
        action_type: Тип действия (rerun, refine, deep_analysis)
        action_data: Дополнительные данные для действия
    
    Returns:
        InlineKeyboardMarkup с кнопками моделей или None
    """
    try:
        balance = await user_repository.get_user_balance(user_id)
        if not balance:
            return None
        
        keyboard_buttons = []
        
        # Проверяем доступные модели
        if balance.get("standard", 0) > 0:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="Standard",
                    callback_data=f"model_{action_type}_{action_data}_standard"
                )
            ])
        
        if balance.get("pro", 0) > 0:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="Pro",
                    callback_data=f"model_{action_type}_{action_data}_pro"
                )
            ])
        
        if balance.get("max", 0) > 0:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="Max",
                    callback_data=f"model_{action_type}_{action_data}_max"
                )
            ])
        
        if not keyboard_buttons:
            return None
        
        # Кнопка "Отмена"
        keyboard_buttons.append([
            InlineKeyboardButton(text="❌ Отмена", callback_data="action_cancel")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры выбора модели: {e}")
        return None


def parse_action_callback(callback_data: str) -> Dict[str, str]:
    """
    Парсит callback_data для интерактивных действий
    
    Args:
        callback_data: Данные callback
    
    Returns:
        Словарь с типом действия и данными
    """
    parts = callback_data.split("_")
    
    if len(parts) < 2:
        return {"type": "unknown", "data": ""}
    
    action_type = parts[1]  # rerun, refine, deep_analysis, etc.
    
    if action_type == "rerun":
        query_id = parts[2] if len(parts) > 2 else "none"
        return {"type": "rerun", "query_id": query_id}
    
    elif action_type == "refine":
        query_id = parts[2] if len(parts) > 2 else "none"
        return {"type": "refine", "query_id": query_id}
    
    elif action_type == "deep":
        if len(parts) > 3 and parts[2] == "analysis":
            startup_id = parts[3] if len(parts) > 3 else ""
            return {"type": "deep_analysis", "startup_id": startup_id}
        elif len(parts) > 2 and parts[2] == "analysis":
            return {"type": "deep_analysis_menu", "data": ""}
    
    elif action_type == "back":
        return {"type": "back_to_results", "data": ""}
    
    elif parts[0] == "model":
        # model_{action_type}_{action_data}_{model}
        if len(parts) >= 4:
            return {
                "type": "model_selected",
                "action_type": parts[1],
                "action_data": parts[2],
                "model": parts[3]
            }
    
    return {"type": "unknown", "data": callback_data}

