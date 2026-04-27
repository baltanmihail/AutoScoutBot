import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from backend.database import async_session, init_db
from backend.models import Startup, ExternalData

ROOT = Path(__file__).resolve().parents[1]
BFO_PATH = ROOT / "db" / "skolkovo_bfo.json"
CHECKO_PATH = ROOT / "db" / "checko_pilot_results.json"

async def main():
    await init_db()

    print("Reading BFO data...")
    if BFO_PATH.exists():
        with open(BFO_PATH, "r", encoding="utf-8") as f:
            bfo_data = json.load(f)
    else:
        bfo_data = {}
        print(f"File not found: {BFO_PATH}")

    print("Reading Checko pilot data...")
    if CHECKO_PATH.exists():
        with open(CHECKO_PATH, "r", encoding="utf-8") as f:
            checko_data = json.load(f)
    else:
        checko_data = []
        print(f"File not found: {CHECKO_PATH}")

    async with async_session() as session:
        # Load all INNs mapping to IDs
        print("Loading INN mapping from DB...")
        res = await session.execute(select(Startup.id, Startup.inn))
        inn_to_id = {}
        for startup_id, inn in res.fetchall():
            if inn:
                inn_to_id[inn] = startup_id

        added_bfo = 0
        added_checko = 0

        for inn, bfo in bfo_data.items():
            startup_id = inn_to_id.get(inn)
            if startup_id:
                ext = ExternalData(
                    startup_id=startup_id,
                    source="bfo",
                    source_authority=0.9,
                    data_json=json.dumps(bfo, ensure_ascii=False)
                )
                session.add(ext)
                added_bfo += 1
        
        for checko_item in checko_data:
            inn = checko_item.get("inn")
            startup_id = inn_to_id.get(inn)
            if startup_id:
                ext = ExternalData(
                    startup_id=startup_id,
                    source="checko",
                    source_authority=0.8,
                    data_json=json.dumps(checko_item, ensure_ascii=False)
                )
                session.add(ext)
                added_checko += 1

        print(f"Committing {added_bfo} BFO records and {added_checko} Checko pilot records...")
        await session.commit()
    print("External Data import complete.")

if __name__ == "__main__":
    asyncio.run(main())