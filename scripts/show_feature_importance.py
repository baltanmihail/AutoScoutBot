"""Show top features for key models."""
import json
from pathlib import Path

models_dir = Path(__file__).resolve().parent.parent / "scoring" / "models"

for target in ["overall", "financial_health", "tech_maturity", "market_potential"]:
    meta_path = models_dir / target / "model_latest_meta.json"
    if not meta_path.exists():
        continue
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    print(f"=== {target} ===")
    print(f"  CV R2: {meta['cv_metrics']['avg_r2']:.4f}")
    print(f"  Top 20 features:")

    raw_imp = meta.get("feature_importance") or meta.get("top_features") or []
    feat_imp = []
    for item in raw_imp:
        if isinstance(item, dict):
            feat_imp.append((item["feature"], item["importance"]))
        else:
            feat_imp.append((item[0], float(item[1])))

    bfo_count = 0
    for name, imp in feat_imp[:20]:
        tag = ""
        if "bfo_" in name:
            tag = " [BFO]"
            bfo_count += 1
        print(f"    {name:<40} {imp:.4f}{tag}")

    total_bfo = sum(1 for n, _ in feat_imp if "bfo_" in n)
    total_bfo_imp = sum(imp for n, imp in feat_imp if "bfo_" in n)
    print(f"  BFO features in top-20: {bfo_count}/20")
    print(f"  Total BFO importance: {total_bfo_imp:.4f} (across {total_bfo} features)")
    print()
