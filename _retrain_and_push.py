"""
One-shot script: retrain all 6 models with XGBoost and push to Git.
Run from project root: python _retrain_and_push.py
"""
import os
import sys
import subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

def run(cmd):
    print(f"\n>>> {cmd}")
    subprocess.run(cmd, shell=True, check=False)

# ──────────────────────────────────────────────────────────────
# Step 0: Ensure xgboost is installed
# ──────────────────────────────────────────────────────────────
try:
    import xgboost
    print(f"✅ xgboost {xgboost.__version__} already installed")
except ImportError:
    print("📦 Installing xgboost...")
    run(f"{sys.executable} -m pip install xgboost>=2.0.0")
    import xgboost
    print(f"✅ xgboost {xgboost.__version__} installed")

# ──────────────────────────────────────────────────────────────
# Step 1: Proxy labeling
# ──────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  AutoScoutBot ML Pipeline -- XGBoost Retraining")
print("=" * 60)

print("\n[1/3] Generating proxy labels from expert data ...")
from scoring.labeler import label_dataframe

csv_path = "SkolkovoStartups.csv"
if not os.path.exists(csv_path):
    print(f"ERROR: {csv_path} not found in {os.getcwd()}")
    sys.exit(1)

labels = label_dataframe(csv_path)
out_path = os.path.join("scoring", "labeled_startups.csv")
labels.to_csv(out_path, index=False, encoding="utf-8")
print(f"  Labeled {len(labels)} startups -> {out_path}")

# ──────────────────────────────────────────────────────────────
# Step 2: Train all 6 models with XGBoost
# ──────────────────────────────────────────────────────────────
print("\n[2/3] Training all 6 scoring models (XGBoost) ...")
from scoring.train import train_multi_target

results = train_multi_target(csv_path, engine="xgboost")

print("\n" + "=" * 60)
print("  TRAINING COMPLETE -- Summary")
print("=" * 60)
for target, info in results.items():
    metrics = info["cv_metrics"]
    r2 = metrics["avg_r2"]
    print(f"\n  {target:25s}  R²={r2:.4f}  MAE={metrics['avg_mae']:.4f}  RMSE={metrics['avg_rmse']:.4f}")
    print(f"  {'':25s}  Top features: {', '.join(f['feature'] for f in info['top_features'])}")

# Verify .joblib files exist
import glob
joblib_files = glob.glob("scoring/models/**/*.joblib", recursive=True)
print(f"\n✅ Model files saved: {len(joblib_files)} .joblib files")
for f in sorted(joblib_files):
    size_kb = os.path.getsize(f) / 1024
    print(f"   {f} ({size_kb:.0f} KB)")

# ──────────────────────────────────────────────────────────────
# Step 3: Git add + commit + push
# ──────────────────────────────────────────────────────────────
print("\n[3/3] Pushing to Git ...")

run('git add -A')
run('git add -f scoring/models/')
run('git commit -m "feat: retrain all 6 models with XGBoost (no LightGBM dep), add xgboost to requirements"')
run('git push origin main')

print("\n" + "=" * 60)
print("  ALL DONE!")
print("  Models retrained with XGBoost (no libgomp needed)")
print("  Docker is removed -- Railway will use fast Nixpacks build")
print("  Wait for Railway to auto-deploy from the new commit")
print("=" * 60)
