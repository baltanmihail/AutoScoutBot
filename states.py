"""
FSM состояния для бота
"""
from aiogram.fsm.state import StatesGroup, State


class SkStates(StatesGroup):
    """Состояния для работы с ботом"""
    FILTERS_CRITERIA = State()
    FILTERS_MENU = State()
    OUTPUT_FORMAT = State()
    AI_FILTERS = State()
    AI_MODEL_SELECTION = State()
    ADMIN_GIVE_REQUESTS = State()
    ADMIN_GIVE_AMOUNT = State()
    # Интерактивные действия после вывода результатов
    ACTION_RERUN = State()  # Повторный поиск
    ACTION_REFINE = State()  # Уточнение запроса
    DEEP_ANALYSIS_SELECTION = State()  # Выбор стартапа для глубокого анализа
    DEEP_ANALYSIS_MODEL = State()  # Выбор модели для глубокого анализа

