"""
Пакетный сбор внешних данных по всем стартапам из базы Сколково.

Использование:
    python scripts/batch_external_fetch.py
    python scripts/batch_external_fetch.py --limit 100
    python scripts/batch_external_fetch.py --limit 50 --delay 2.0 --output data/external_batch.jsonl

Собранные данные сохраняются в external_batch.jsonl (или в таблицу SQLite).
Дальше можно сравнить ML-оценки по «Сколково + внешние данные» с эталонными метками Сколково
и при необходимости дообучить модель (scoring/retrain.py), не трогая продакшен до проверки метрик.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_skolkovo_list(limit: int | None):
    """Загружает список стартапов Сколково с непустым ИНН."""
    try:
        from utils.startup_utils import load_skolkovo_database
        db, _ = load_skolkovo_database()
        if not db:
            logger.error("База Сколково не загружена")
            return []
        out = []
        for s in db:
            inn = str(s.get("inn", "")).strip()
            if not inn or len(inn) < 10:
                continue
            out.append({
                "inn": inn,
                "name": s.get("name", ""),
                "id": s.get("id", ""),
            })
        if limit:
            out = out[:limit]
        logger.info("Загружено %s стартапов с ИНН (лимит=%s)", len(out), limit)
        return out
    except Exception as e:
        logger.exception("Ошибка загрузки Сколково: %s", e)
        return []


async def fetch_and_save_one(mgr, startup: dict, out_path: Path, delay: float):
    """Собрать данные по одному стартапу и дописать в JSONL."""
    inn = startup["inn"]
    name = startup.get("name", "")
    try:
        data = await mgr.fetch_all(inn=inn, company_name=name)
        if not data:
            return False
        record = {
            "inn": inn,
            "name": name,
            "skolkovo_id": startup.get("id", ""),
            "external": data,
        }
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        logger.warning("Ошибка для ИНН %s (%s): %s", inn, name[:40], e)
        return False
    finally:
        if delay > 0:
            await asyncio.sleep(delay)


async def run_batch(
    limit: int | None = None,
    delay: float = 1.0,
    output: str | Path = "external_batch.jsonl",
):
    startups = load_skolkovo_list(limit)
    if not startups:
        return

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from parsers.manager import ParserManager
    mgr = ParserManager()
    try:
        ok = 0
        for i, s in enumerate(startups):
            if (i + 1) % 50 == 0:
                logger.info("Обработано %s / %s", i + 1, len(startups))
            if await fetch_and_save_one(mgr, s, out_path, delay):
                ok += 1
        logger.info("Готово: успешно %s из %s, файл %s", ok, len(startups), out_path)
    finally:
        await mgr.close()


def main():
    os.chdir(ROOT)  # чтобы SKOLKOVO_DATABASE_PATH и config находили файлы
    p = argparse.ArgumentParser(description="Пакетный сбор внешних данных по стартапам Сколково")
    p.add_argument("--limit", type=int, default=None, help="Макс. число стартапов (для теста)")
    p.add_argument("--delay", type=float, default=1.0, help="Задержка между запросами (сек)")
    p.add_argument("--output", type=str, default="external_batch.jsonl", help="Выходной JSONL файл")
    args = p.parse_args()
    asyncio.run(run_batch(limit=args.limit, delay=args.delay, output=args.output))


if __name__ == "__main__":
    main()
