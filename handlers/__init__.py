"""
Модуль обработчиков для Telegram бота
"""
from .start import register_start_handlers
from .search import register_search_handlers, start_search_func
from .filters import register_filters_handlers
from .interactive import register_interactive_handlers
from .admin import register_admin_handlers

__all__ = [
    'register_start_handlers',
    'register_search_handlers',
    'start_search_func',
    'register_filters_handlers',
    'register_interactive_handlers',
    'register_admin_handlers',
]
