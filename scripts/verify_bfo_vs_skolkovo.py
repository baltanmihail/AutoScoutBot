"""
Compare BFO data from Checko API vs SkolkovoStartups.csv to verify accuracy.
"""
import json
import pandas as pd
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    with open(ROOT / "skolkovo_bfo.json", encoding="utf-8") as f:
        bfo = json.load(f)

    df = pd.read_csv(ROOT / "SkolkovoStartups.csv", encoding="utf-8", dtype=str).fillna("")

    inn_col = [c for c in df.columns if c.strip().upper() in ("ИНН", "INN")][0]

    matched = 0
    exact = 0
    unit_diff = 0
    mismatch = 0
    examples_match = []
    examples_unit = []
    examples_mismatch = []
    ratios = []

    for _, row in df.iterrows():
        inn = str(row[inn_col]).strip()
        if not inn or inn not in bfo or not bfo[inn]:
            continue

        checko_data = bfo[inn]

        for year in ["2024", "2023", "2022", "2021", "2020"]:
            sk_rev_col = "Выручка " + year
            if sk_rev_col not in df.columns:
                continue

            sk_rev_str = str(row.get(sk_rev_col, "")).strip()
            if not sk_rev_str or sk_rev_str == "nan":
                continue

            if year not in checko_data:
                continue

            checko_rev = checko_data[year].get("revenue")
            if checko_rev is None:
                continue

            try:
                sk_rev = float(sk_rev_str.replace(" ", "").replace(",", "."))
            except ValueError:
                continue

            if abs(sk_rev) < 1 and abs(checko_rev) < 1:
                exact += 1
                matched += 1
                continue

            if abs(sk_rev) < 1:
                matched += 1
                mismatch += 1
                continue

            ratio = checko_rev / sk_rev
            ratios.append(ratio)
            matched += 1

            if 0.99 < ratio < 1.01:
                exact += 1
                if len(examples_match) < 3:
                    examples_match.append(
                        f"  INN={inn} {year}: SK={sk_rev:,.0f}  Checko={checko_rev:,.0f}  ratio={ratio:.4f}"
                    )
            elif 0.95 < abs(ratio / 1000) < 1.05 or 0.95 < abs(ratio * 1000) < 1.05:
                unit_diff += 1
                if len(examples_unit) < 5:
                    examples_unit.append(
                        f"  INN={inn} {year}: SK={sk_rev:,.0f}  Checko={checko_rev:,.0f}  ratio={ratio:.2f}"
                    )
            else:
                mismatch += 1
                if len(examples_mismatch) < 5:
                    examples_mismatch.append(
                        f"  INN={inn} {year}: SK={sk_rev:,.0f}  Checko={checko_rev:,.0f}  ratio={ratio:.2f}"
                    )

    print(f"Matched pairs (INN+year with both revenue): {matched}")
    print(f"  Exact match (<1%): {exact} ({exact/max(matched,1)*100:.1f}%)")
    print(f"  Unit difference (x1000): {unit_diff} ({unit_diff/max(matched,1)*100:.1f}%)")
    print(f"  Other mismatch: {mismatch} ({mismatch/max(matched,1)*100:.1f}%)")
    print()

    if ratios:
        import statistics
        print(f"Ratio Checko/Skolkovo statistics (n={len(ratios)}):")
        print(f"  Median: {statistics.median(ratios):.4f}")
        print(f"  Mean:   {statistics.mean(ratios):.4f}")
        sorted_r = sorted(ratios)
        print(f"  P10:    {sorted_r[len(sorted_r)//10]:.4f}")
        print(f"  P90:    {sorted_r[9*len(sorted_r)//10]:.4f}")

    if examples_match:
        print("\nExact matches:")
        for e in examples_match:
            print(e)
    if examples_unit:
        print("\nUnit differences (likely thousands vs rubles):")
        for e in examples_unit:
            print(e)
    if examples_mismatch:
        print("\nOther mismatches:")
        for e in examples_mismatch:
            print(e)

    # Also check profit
    print("\n" + "="*60)
    print("PROFIT comparison:")
    prof_matched = 0
    prof_exact = 0
    prof_close = 0
    prof_ratios = []

    for _, row in df.iterrows():
        inn = str(row[inn_col]).strip()
        if not inn or inn not in bfo or not bfo[inn]:
            continue
        checko_data = bfo[inn]
        for year in ["2024", "2023", "2022", "2021", "2020"]:
            sk_col = "Прибыль " + year
            if sk_col not in df.columns:
                continue
            sk_str = str(row.get(sk_col, "")).strip()
            if not sk_str or sk_str == "nan":
                continue
            if year not in checko_data:
                continue
            checko_val = checko_data[year].get("net_profit")
            if checko_val is None:
                continue
            try:
                sk_val = float(sk_str.replace(" ", "").replace(",", "."))
            except ValueError:
                continue
            prof_matched += 1
            if abs(sk_val) < 1 and abs(checko_val) < 1:
                prof_exact += 1
                continue
            if abs(sk_val) < 1:
                continue
            ratio = checko_val / sk_val
            prof_ratios.append(ratio)
            if 0.99 < ratio < 1.01:
                prof_exact += 1
            elif 0.95 < abs(ratio / 1000) < 1.05:
                prof_close += 1

    print(f"  Matched: {prof_matched}")
    print(f"  Exact (<1%): {prof_exact} ({prof_exact/max(prof_matched,1)*100:.1f}%)")
    print(f"  Unit diff (x1000): {prof_close} ({prof_close/max(prof_matched,1)*100:.1f}%)")
    if prof_ratios:
        import statistics
        print(f"  Median ratio: {statistics.median(prof_ratios):.4f}")


if __name__ == "__main__":
    main()
