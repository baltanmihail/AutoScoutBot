import asyncio
import json
import random

from parsers.manager import ParserManager
from utils.startup_utils import load_skolkovo_database


async def main():
    sk_db, _ = load_skolkovo_database()
    if not sk_db:
        print("❌ Не удалось загрузить базу Сколково")
        return

    # Берём только стартапы с ИНН
    startups_with_inn = [s for s in sk_db if str(s.get("inn", "")).strip()]
    total = len(startups_with_inn)
    print(f"Найдено {total} стартапов с ИНН")

    sample_size = min(30, total)
    sample = random.sample(startups_with_inn, sample_size)

    mgr = ParserManager()
    results = []

    for idx, s in enumerate(sample, 1):
        inn = str(s.get("inn", "")).strip()
        name = s.get("name", "")
        print(f"\n[{idx}/{sample_size}] INN={inn} NAME={name}")
        try:
            data = await mgr.fetch_all(inn=inn, company_name=name)
            sources = [k for k, v in data.items() if v]
            print("  Источники с данными:", ", ".join(sources) or "нет")
            results.append({"inn": inn, "name": name, "external": data})
        except Exception as e:
            print(f"  Ошибка для INN={inn}: {e}")

    await mgr.close()

    with open("checko_pilot_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Сохранено {len(results)} записей в checko_pilot_results.json")


if __name__ == "__main__":
    asyncio.run(main())

