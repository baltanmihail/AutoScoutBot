"""
Утилиты для работы со стартапами, форматирования и экспорта
"""
from .startup_utils import (
    format_date,
    load_skolkovo_database,
    extract_level_value,
    parse_profit,
    get_max_profit,
    determine_stage,
    calculate_financial_stability,
    calculate_patent_score,
    analyze_startup,
)
from .formatters import (
    remove_emojis,
    escape_html,
)
from .excel_generator import (
    generate_csv,
    generate_excel,
)

__all__ = [
    'format_date',
    'load_skolkovo_database',
    'extract_level_value',
    'parse_profit',
    'get_max_profit',
    'determine_stage',
    'calculate_financial_stability',
    'calculate_patent_score',
    'analyze_startup',
    'remove_emojis',
    'escape_html',
    'generate_csv',
    'generate_excel',
]

