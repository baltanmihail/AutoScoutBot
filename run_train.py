"""
Runner script: label data + train ALL 6 scoring models + show metrics.
Run from project root: python run_train.py
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

print("=" * 60)
print("  AutoScoutBot ML Pipeline")
print("  Training on 5166 Skolkovo expert-labeled startups")
print("  All 6 scoring dimensions")
print("=" * 60)

# Step 1: Proxy labeling
print("\n[1/2] Generating scores from expert data ...")
from scoring.labeler import label_dataframe

csv_path = "SkolkovoStartups.csv"
if not os.path.exists(csv_path):
    print(f"ERROR: {csv_path} not found in {os.getcwd()}")
    sys.exit(1)

labels = label_dataframe(csv_path)
out_path = os.path.join("scoring", "labeled_startups.csv")
labels.to_csv(out_path, index=False, encoding="utf-8")
print(f"  Labeled {len(labels)} startups -> {out_path}")

print("\n  Score distribution:")
for col in [c for c in labels.columns if c.startswith("score_")]:
    print(f"    {col:30s}  mean={labels[col].mean():.2f}  min={labels[col].min():.2f}  max={labels[col].max():.2f}")

# Step 2: Train ALL 6 models
print("\n[2/2] Training all 6 scoring models ...")
from scoring.train import train_multi_target

results = train_multi_target(csv_path, engine="xgboost")

print("\n" + "=" * 60)
print("  TRAINING COMPLETE -- Summary")
print("=" * 60)
for target, info in results.items():
    metrics = info["cv_metrics"]
    print(f"\n  {target:25s}  MAE={metrics['avg_mae']:.4f}  RMSE={metrics['avg_rmse']:.4f}")
    print(f"  {'':25s}  Top features: {', '.join(f['feature'] for f in info['top_features'])}")

print(f"\nAll models saved to: scoring/models/")
print("Ready for deployment!")
