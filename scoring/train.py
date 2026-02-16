"""
Phase 2 -- Model Training Pipeline.

Trains an XGBoost regressor on the proxy-labeled Skolkovo data.
Supports:
    * 5-fold cross-validation with MAE / RMSE metrics
    * Optional LightGBM fallback
    * Model versioning (saved as JSON metadata alongside the .joblib model)
    * Feature importance report

Usage:
    python -m scoring.train                          # defaults
    python -m scoring.train --csv path.csv           # custom CSV
    python -m scoring.train --model-dir scoring/models --engine lightgbm
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.model_selection import KFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scoring.features import build_feature_matrix, get_feature_names


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_xgboost(
    X: np.ndarray,
    y: np.ndarray,
    n_folds: int = 5,
    random_state: int = 42,
) -> tuple:
    """
    Train XGBoost regressor with k-fold cross-validation.

    Returns:
        model       -- fitted XGBRegressor on FULL data
        cv_metrics  -- dict with per-fold and average MAE / RMSE / R2
    """
    import xgboost as xgb

    params = dict(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=random_state,
        n_jobs=-1,
    )

    kf = KFold(n_splits=n_folds, shuffle=True, random_state=random_state)
    fold_metrics = []

    print(f"\n{'='*60}")
    print(f"Training XGBoost  |  {n_folds}-fold CV  |  {X.shape[0]} samples, {X.shape[1]} features")
    print(f"{'='*60}")

    for fold_idx, (train_idx, val_idx) in enumerate(kf.split(X)):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        model = xgb.XGBRegressor(**params)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        y_pred = model.predict(X_val)
        mae = mean_absolute_error(y_val, y_pred)
        rmse = float(np.sqrt(mean_squared_error(y_val, y_pred)))
        r2 = float(r2_score(y_val, y_pred))

        fold_metrics.append({"fold": fold_idx + 1, "mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4)})
        print(f"  Fold {fold_idx + 1}/{n_folds}:  MAE={mae:.4f}  RMSE={rmse:.4f}  R2={r2:.4f}")

    avg_mae = np.mean([m["mae"] for m in fold_metrics])
    avg_rmse = np.mean([m["rmse"] for m in fold_metrics])
    avg_r2 = np.mean([m["r2"] for m in fold_metrics])
    print(f"\n  Average:  MAE={avg_mae:.4f}  RMSE={avg_rmse:.4f}  R2={avg_r2:.4f}")

    # Retrain on full data
    print("\nRetraining on full dataset ...")
    final_model = xgb.XGBRegressor(**params)
    final_model.fit(X, y, verbose=False)

    cv_metrics = {
        "folds": fold_metrics,
        "avg_mae": round(float(avg_mae), 4),
        "avg_rmse": round(float(avg_rmse), 4),
        "avg_r2": round(float(avg_r2), 4),
    }

    return final_model, cv_metrics


def train_lightgbm(
    X: np.ndarray,
    y: np.ndarray,
    n_folds: int = 5,
    random_state: int = 42,
) -> tuple:
    """
    Train LightGBM regressor with k-fold cross-validation (fallback engine).
    """
    import lightgbm as lgb

    params = dict(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=random_state,
        n_jobs=-1,
        verbose=-1,
    )

    kf = KFold(n_splits=n_folds, shuffle=True, random_state=random_state)
    fold_metrics = []

    print(f"\n{'='*60}")
    print(f"Training LightGBM  |  {n_folds}-fold CV  |  {X.shape[0]} samples, {X.shape[1]} features")
    print(f"{'='*60}")

    for fold_idx, (train_idx, val_idx) in enumerate(kf.split(X)):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        model = lgb.LGBMRegressor(**params)
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)])

        y_pred = model.predict(X_val)
        mae = mean_absolute_error(y_val, y_pred)
        rmse = float(np.sqrt(mean_squared_error(y_val, y_pred)))
        r2 = float(r2_score(y_val, y_pred))

        fold_metrics.append({"fold": fold_idx + 1, "mae": round(mae, 4), "rmse": round(rmse, 4), "r2": round(r2, 4)})
        print(f"  Fold {fold_idx + 1}/{n_folds}:  MAE={mae:.4f}  RMSE={rmse:.4f}  R2={r2:.4f}")

    avg_mae = np.mean([m["mae"] for m in fold_metrics])
    avg_rmse = np.mean([m["rmse"] for m in fold_metrics])
    avg_r2 = np.mean([m["r2"] for m in fold_metrics])
    print(f"\n  Average:  MAE={avg_mae:.4f}  RMSE={avg_rmse:.4f}  R2={avg_r2:.4f}")

    print("\nRetraining on full dataset ...")
    final_model = lgb.LGBMRegressor(**params)
    final_model.fit(X, y)

    cv_metrics = {
        "folds": fold_metrics,
        "avg_mae": round(float(avg_mae), 4),
        "avg_rmse": round(float(avg_rmse), 4),
        "avg_r2": round(float(avg_r2), 4),
    }

    return final_model, cv_metrics


# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

def feature_importance_report(model, feature_names: list[str], top_n: int = 15) -> list[dict]:
    """Extract top-N feature importances from a tree model."""
    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1][:top_n]
    report = []
    for i in indices:
        report.append({
            "feature": feature_names[i],
            "importance": round(float(importances[i]), 4),
        })
    return report


# ---------------------------------------------------------------------------
# Save / versioning
# ---------------------------------------------------------------------------

def save_model(
    model,
    cv_metrics: dict,
    feature_names: list[str],
    importance: list[dict],
    engine: str,
    model_dir: Path,
) -> str:
    """
    Save model and metadata. Returns the version string.
    """
    model_dir.mkdir(parents=True, exist_ok=True)
    version = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    model_path = model_dir / f"model_{version}.joblib"
    meta_path = model_dir / f"model_{version}_meta.json"

    joblib.dump(model, model_path)

    meta = {
        "version": version,
        "engine": engine,
        "created_at": dt.datetime.now().isoformat(),
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "cv_metrics": cv_metrics,
        "top_features": importance,
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # Symlink / copy as "latest"
    latest_model = model_dir / "model_latest.joblib"
    latest_meta = model_dir / "model_latest_meta.json"

    # On Windows, copy instead of symlink
    import shutil
    shutil.copy2(model_path, latest_model)
    shutil.copy2(meta_path, latest_meta)

    print(f"\nModel saved:")
    print(f"  {model_path}")
    print(f"  {meta_path}")
    print(f"  Version: {version}")

    return version


# ---------------------------------------------------------------------------
# Multi-target training (train separate models for each score dimension)
# ---------------------------------------------------------------------------

def train_multi_target(
    csv_path: str | Path,
    engine: str = "xgboost",
    model_dir: Path | None = None,
) -> dict:
    """
    Train models for all 6 scoring dimensions:
        overall, tech_maturity, innovation, market_potential,
        team_readiness, financial_health

    Returns dict with version and metrics for each target.
    """
    from scoring.labeler import label_dataframe

    if model_dir is None:
        model_dir = ROOT / "scoring" / "models"

    # Build features
    X, feature_names, ids, y_overall = build_feature_matrix(csv_path)

    # Get all target columns from labels
    labels_df = label_dataframe(csv_path)
    label_map = {r["id"]: r for _, r in labels_df.iterrows()}

    targets = {
        "overall": y_overall,
    }

    for target_name in ["tech_maturity", "innovation", "market_potential",
                        "team_readiness", "financial_health"]:
        col = f"score_{target_name}"
        y_target = np.array([
            float(label_map.get(sid, {}).get(col, 3.0))
            if sid in label_map and len(label_map[sid]) > 0 else 3.0
            for sid in ids
        ], dtype=np.float32)
        targets[target_name] = y_target

    results = {}
    train_fn = train_xgboost if engine == "xgboost" else train_lightgbm

    for target_name, y in targets.items():
        print(f"\n{'#'*60}")
        print(f"# Target: {target_name}")
        print(f"{'#'*60}")

        model, cv_metrics = train_fn(X, y)
        importance = feature_importance_report(model, feature_names)

        target_dir = model_dir / target_name
        version = save_model(
            model, cv_metrics, feature_names, importance,
            engine=engine, model_dir=target_dir,
        )

        results[target_name] = {
            "version": version,
            "cv_metrics": cv_metrics,
            "top_features": importance[:5],
        }

    # Save a summary
    summary_path = model_dir / "training_summary.json"
    summary = {
        "engine": engine,
        "trained_at": dt.datetime.now().isoformat(),
        "n_samples": X.shape[0],
        "n_features": X.shape[1],
        "targets": results,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nTraining summary -> {summary_path}")

    return results


# ---------------------------------------------------------------------------
# Convenience wrappers (used by run_train.py)
# ---------------------------------------------------------------------------

def train_and_evaluate(
    csv_path: str | Path,
    n_folds: int = 5,
    engine: str = "lightgbm",
) -> tuple:
    """
    High-level wrapper: build features from CSV, train model, return (model, metrics).

    Tries LightGBM first, falls back to XGBoost if unavailable.
    The returned metrics dict contains: avg_mae, avg_rmse, avg_r2, folds.
    """
    X, feature_names, ids, y = build_feature_matrix(csv_path)

    # Pick engine
    if engine == "lightgbm":
        try:
            import lightgbm  # noqa: F401
            model, metrics = train_lightgbm(X, y, n_folds=n_folds)
            metrics["engine"] = "lightgbm"
        except ImportError:
            print("  LightGBM not available, falling back to XGBoost ...")
            model, metrics = train_xgboost(X, y, n_folds=n_folds)
            metrics["engine"] = "xgboost"
    else:
        try:
            import xgboost  # noqa: F401
            model, metrics = train_xgboost(X, y, n_folds=n_folds)
            metrics["engine"] = "xgboost"
        except ImportError:
            print("  XGBoost not available, falling back to LightGBM ...")
            model, metrics = train_lightgbm(X, y, n_folds=n_folds)
            metrics["engine"] = "lightgbm"

    # Attach feature info for save_model
    metrics["_feature_names"] = feature_names
    metrics["_importance"] = feature_importance_report(model, feature_names)

    return model, metrics


# Overloaded save_model that accepts (model, metrics) for run_train.py compat
_original_save_model = save_model


def save_model(
    model,
    cv_metrics_or_feature_names=None,
    feature_names=None,
    importance=None,
    engine=None,
    model_dir=None,
) -> str:
    """
    Save model and metadata.

    Supports two calling conventions:
        save_model(model, metrics)                        -- from run_train.py
        save_model(model, cv_metrics, feature_names, ...) -- full signature
    """
    # Detect the simple (model, metrics) call from run_train.py
    if isinstance(cv_metrics_or_feature_names, dict) and "_feature_names" in cv_metrics_or_feature_names:
        metrics = cv_metrics_or_feature_names
        feat_names = metrics.pop("_feature_names")
        imp = metrics.pop("_importance")
        eng = metrics.pop("engine", "lightgbm")
        mdir = Path(model_dir) if model_dir else ROOT / "scoring" / "models" / "overall"
        return _original_save_model(model, metrics, feat_names, imp, engine=eng, model_dir=mdir)

    # Full signature (from train_multi_target / CLI)
    return _original_save_model(
        model, cv_metrics_or_feature_names, feature_names, importance,
        engine=engine, model_dir=model_dir,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train scoring models for AutoScoutBot")
    parser.add_argument("--csv", default=str(ROOT / "SkolkovoStartups.csv"))
    parser.add_argument("--model-dir", default=str(ROOT / "scoring" / "models"))
    parser.add_argument("--engine", choices=["xgboost", "lightgbm"], default="xgboost")
    parser.add_argument("--single-target", action="store_true",
                        help="Train only the overall score model (faster)")
    args = parser.parse_args()

    model_dir = Path(args.model_dir)

    if args.single_target:
        X, feature_names, ids, y = build_feature_matrix(args.csv)
        train_fn = train_xgboost if args.engine == "xgboost" else train_lightgbm
        model, cv_metrics = train_fn(X, y)
        importance = feature_importance_report(model, feature_names)
        save_model(
            model, cv_metrics, feature_names, importance,
            engine=args.engine, model_dir=model_dir / "overall",
        )
    else:
        train_multi_target(args.csv, engine=args.engine, model_dir=model_dir)


if __name__ == "__main__":
    main()
