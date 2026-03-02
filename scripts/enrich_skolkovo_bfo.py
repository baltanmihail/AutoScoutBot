"""
Enrich Skolkovo startups with BFO financial data from Checko API.

Collects /finances for each startup with a valid INN and saves
to a JSON file (inn -> financials mapping).

This mapping is then used by features.py during training to compute
58 financial ratio features.

Usage:
    python scripts/enrich_skolkovo_bfo.py --limit 100 --delay 0.3
    python scripts/enrich_skolkovo_bfo.py               # all startups
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_inns(csv_path: str, limit: int | None = None) -> list[str]:
    """Load unique non-empty INNs from SkolkovoStartups.csv."""
    import pandas as pd
    df = pd.read_csv(csv_path, encoding="utf-8", dtype=str).fillna("")
    col = None
    for c in df.columns:
        if c.strip().upper() in ("\u0418\u041d\u041d", "INN", "inn"):
            col = c
            break
    if col is None:
        logger.error("Column INN not found in CSV")
        return []

    inns = df[col].str.strip().unique().tolist()
    inns = [i for i in inns if i and len(i) >= 10]
    logger.info("Found %d unique INNs in CSV", len(inns))

    if limit:
        inns = inns[:limit]
    return inns


async def fetch_bfo(inn: str, parser) -> dict:
    """Fetch Checko /finances and return raw financials dict."""
    try:
        data = await parser.fetch(inn)
        return data.get("financials", {})
    except Exception as e:
        logger.warning("Error for INN %s: %s", inn, e)
        return {}


async def run(args):
    os.chdir(ROOT)

    from config import CHECKO_API_KEYS
    from parsers.checko_parser import CheckoParser

    csv_path = args.csv or str(ROOT / "SkolkovoStartups.csv")
    output_path = Path(args.output)

    existing = {}
    if output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            existing = json.load(f)
        logger.info("Loaded %d existing entries from %s", len(existing), output_path)

    inns = load_inns(csv_path, args.limit)
    inns_to_fetch = [i for i in inns if i not in existing]
    logger.info("Need to fetch: %d (already have: %d)", len(inns_to_fetch), len(existing))

    if not inns_to_fetch:
        logger.info("All INNs already fetched")
        return

    parser = CheckoParser(api_key=CHECKO_API_KEYS)

    ok = 0
    empty = 0
    errors = 0

    try:
        for i, inn in enumerate(inns_to_fetch):
            if (i + 1) % 100 == 0:
                logger.info("Progress: %d / %d (ok=%d, empty=%d)", i + 1, len(inns_to_fetch), ok, empty)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False)

            try:
                financials = await fetch_bfo(inn, parser)
                str_keyed = {str(k): v for k, v in financials.items()}
                existing[inn] = str_keyed

                if financials:
                    ok += 1
                else:
                    empty += 1
            except RuntimeError as e:
                if "limit" in str(e).lower() or "все ключи исчерпаны" in str(e):
                    logger.warning("Checko: все ключи исчерпаны после %d запросов. Сохраняем и останавливаем.", ok + empty)
                    break
                existing[inn] = {}
                errors += 1
            except Exception as e:
                logger.warning("INN %s: %s", inn, e)
                existing[inn] = {}
                errors += 1

            if args.delay > 0:
                await asyncio.sleep(args.delay)
    finally:
        cost = parser.estimate_paid_cost()
        if cost > 0:
            logger.info("Checko (платный ключ): ~%.2f ₽ за эту сессию", cost)
        await parser.close()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False)

    logger.info(
        "Done: %d fetched (%d with data, %d empty, %d errors). Total in file: %d",
        ok + empty + errors, ok, empty, errors, len(existing),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--delay", type=float, default=0.3)
    p.add_argument("--output", default="skolkovo_bfo.json")
    args = p.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
