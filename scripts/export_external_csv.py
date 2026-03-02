"""
Export external_batch.jsonl to a readable CSV file.

Columns:
  inn, name, year_founded, status, okved, years_financial,
  revenue_latest, profit_latest, total_assets, equity,
  egrul_active, news_count, moex_ticker

Usage:
  python scripts/export_external_csv.py
  python scripts/export_external_csv.py --input external_batch.jsonl --output external_startups.csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def flatten_row(row: dict) -> dict:
    ext = row.get("external", {})
    checko = ext.get("checko", {})
    egrul = ext.get("egrul", {})
    news = ext.get("news", {})
    moex = ext.get("moex", {})

    name = checko.get("name") or egrul.get("name") or row.get("name", "")
    year_founded = checko.get("year_founded", "")
    status = checko.get("status", egrul.get("status", ""))
    is_active = checko.get("is_active", egrul.get("is_active", ""))
    okved = checko.get("okved_name", "")

    financials = checko.get("financials", {})
    fin_years = sorted(financials.keys()) if financials else []

    latest = {}
    if fin_years:
        latest = financials[max(fin_years)]

    return {
        "inn": row.get("inn", ""),
        "skolkovo_id": row.get("skolkovo_id", ""),
        "name": name,
        "year_founded": year_founded,
        "status": status,
        "is_active": is_active,
        "okved": okved[:60] if okved else "",
        "fin_years": f"{min(fin_years)}-{max(fin_years)}" if fin_years else "",
        "fin_years_count": len(fin_years),
        "revenue_latest": latest.get("revenue", ""),
        "profit_latest": latest.get("net_profit", ""),
        "total_assets": latest.get("total_assets", ""),
        "equity": latest.get("equity", ""),
        "cash": latest.get("cash", ""),
        "egrul_name": egrul.get("name", ""),
        "egrul_ogrn": egrul.get("ogrn", ""),
        "news_count": news.get("total_count", 0),
        "moex_ticker": moex.get("ticker", ""),
    }


def main():
    parser = argparse.ArgumentParser(description="Export external batch to CSV")
    parser.add_argument("--input", default="external_batch.jsonl")
    parser.add_argument("--output", default="external_startups.csv")
    args = parser.parse_args()

    import os
    os.chdir(ROOT)

    inp = Path(args.input)
    if not inp.exists():
        print(f"File not found: {inp}")
        return

    rows = load_jsonl(inp)
    if not rows:
        print("No data in JSONL")
        return

    flat = [flatten_row(r) for r in rows]
    fields = list(flat[0].keys())

    out = Path(args.output)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flat)

    with_revenue = sum(1 for r in flat if r.get("revenue_latest"))
    print(f"Exported {len(flat)} startups to {out}")
    print(f"  With financial data: {with_revenue}")
    print(f"  With EGRUL: {sum(1 for r in flat if r.get('egrul_ogrn'))}")
    print(f"  With news: {sum(1 for r in flat if r.get('news_count'))}")


if __name__ == "__main__":
    main()
