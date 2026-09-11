"""Идентификация показателей бухгалтерской (финансовой) отчётности.

Строка 1700 формы 1 — «БАЛАНС (пассив)», то есть итог пассива: собственный
капитал (1300) вместе с долгосрочными (1400) и краткосрочными (1500)
обязательствами. Обязательствами является только сумма строк 1400 и 1500.
Отождествление строки 1700 с обязательствами доводит долговую нагрузку до
единицы у любой компании и смещает производные индикаторы риска, не порождая
при этом признаков сбоя: индикатор продолжает выдавать правдоподобные числа.

Модуль служит единственной точкой разрешения этой неоднозначности, включая
ранее сохранённые выгрузки, где под ключом total_liabilities хранится итог
пассива баланса, а строка 1400 отсутствует.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

TOLERANCE = 0.01


def _num(data: dict, *keys: str) -> Optional[float]:
    """Первое доступное численное значение по списку ключей."""
    for key in keys:
        val = data.get(key)
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val.replace(" ", "").replace("\xa0", "").replace(",", "."))
            except ValueError:
                continue
    return None


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE * max(abs(a), abs(b), 1.0)


def resolve_balance_total(data: dict) -> Optional[float]:
    """Итог пассива баланса (строка 1700).

    В унаследованных выгрузках он может лежать под ключом total_liabilities:
    признаком этого служит совпадение значения с итогом актива.
    """
    balance_total = _num(data, "1700", "balance_total")
    if balance_total is not None:
        return balance_total

    legacy = _num(data, "total_liabilities")
    assets = _num(data, "1600", "total_assets")
    if legacy is not None and assets is not None and _close(legacy, assets):
        return legacy
    return None


def resolve_obligations(data: dict) -> Optional[float]:
    """Сумма обязательств (строки 1400 и 1500).

    Порядок разрешения:
      1. явная сумма долгосрочных и краткосрочных обязательств;
      2. итог пассива баланса минус собственный капитал — учитывает
         долгосрочные обязательства даже там, где строка 1400 отсутствует;
      3. только краткосрочные обязательства как последнее приближение.
    """
    long_term = _num(data, "1400", "long_term_liabilities")
    current = _num(data, "1500", "current_liabilities")
    if long_term is not None and current is not None:
        return max(long_term + current, 0.0)

    equity = _num(data, "1300", "equity")
    balance_total = resolve_balance_total(data)
    if balance_total is not None and equity is not None:
        return max(balance_total - equity, 0.0)

    if current is not None:
        return max(current, 0.0)
    if long_term is not None:
        return max(long_term, 0.0)
    return None


def check_identities(data: dict) -> Dict[str, Tuple[bool, Optional[float], Optional[float]]]:
    """Контрольные тождества отчётности.

    Нарушение любого из них означает, что показатели распознаны неверно и
    производные индикаторы риска использовать нельзя. Возвращает отображение
    «название тождества → (выполнено, левая часть, правая часть)»; тождества,
    для проверки которых не хватает данных, в результат не попадают.
    """
    assets = _num(data, "1600", "total_assets")
    balance_total = resolve_balance_total(data)
    equity = _num(data, "1300", "equity")
    long_term = _num(data, "1400", "long_term_liabilities")
    current = _num(data, "1500", "current_liabilities")
    non_current_assets = _num(data, "1100", "non_current_assets")
    current_assets = _num(data, "1200", "current_assets")

    result: Dict[str, Tuple[bool, Optional[float], Optional[float]]] = {}

    if assets is not None and balance_total is not None:
        result["актив равен пассиву"] = (_close(assets, balance_total), assets, balance_total)

    if balance_total is not None and equity is not None and long_term is not None and current is not None:
        right = equity + long_term + current
        result["пассив равен сумме капитала и обязательств"] = (
            _close(balance_total, right), balance_total, right,
        )

    if assets is not None and non_current_assets is not None and current_assets is not None:
        right = non_current_assets + current_assets
        result["актив равен сумме внеоборотных и оборотных активов"] = (
            _close(assets, right), assets, right,
        )

    obligations = resolve_obligations(data)
    if obligations is not None:
        result["обязательства неотрицательны"] = (obligations >= 0.0, obligations, 0.0)

    # При отрицательном собственном капитале обязательства правомерно
    # превышают итог баланса, поэтому сопоставление имеет смысл только
    # при неотрицательном капитале.
    if (obligations is not None and balance_total is not None
            and equity is not None and equity >= 0):
        result["обязательства не превышают итог пассива"] = (
            obligations <= balance_total * (1.0 + TOLERANCE), obligations, balance_total,
        )

    return result


def identity_violations(data: dict) -> list[str]:
    """Названия нарушенных контрольных тождеств."""
    return [name for name, (ok, _, _) in check_identities(data).items() if not ok]
