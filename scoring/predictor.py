"""
Phase 2 -- Prediction Service + SHAP Explanations.

Loads trained models and provides:
    predict(row)      -> dict of scores
    explain(row)      -> dict of SHAP feature contributions

Thread-safe singleton that lazily loads models on first call.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DIR = ROOT / "scoring" / "models"

TARGET_NAMES = [
    "overall",
    "tech_maturity",
    "innovation",
    "market_potential",
    "team_readiness",
    "financial_health",
]


class StartupPredictor:
    """
    Loads XGBoost / LightGBM models and computes predictions + SHAP explanations.
    """

    def __init__(self, model_dir: Path | str | None = None):
        self._model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        self._models: dict = {}
        self._meta: dict = {}
        self._explainers: dict = {}
        self._feature_names: list[str] = []
        self._loaded = False
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_models()
            self._loaded = True

    def _load_models(self):
        """Load all target models from disk."""
        import joblib

        loaded = 0
        for target in TARGET_NAMES:
            model_path = self._model_dir / target / "model_latest.joblib"
            meta_path = self._model_dir / target / "model_latest_meta.json"

            if not model_path.exists():
                logger.warning("Model not found for target '%s': %s", target, model_path)
                continue

            self._models[target] = joblib.load(model_path)

            if meta_path.exists():
                self._meta[target] = json.loads(meta_path.read_text(encoding="utf-8"))
                if not self._feature_names and "feature_names" in self._meta[target]:
                    self._feature_names = self._meta[target]["feature_names"]

            loaded += 1

        logger.info("Loaded %d/%d scoring models from %s", loaded, len(TARGET_NAMES), self._model_dir)

    @property
    def is_ready(self) -> bool:
        """True if at least the 'overall' model is loaded."""
        self._ensure_loaded()
        return "overall" in self._models

    @property
    def version(self) -> Optional[str]:
        """Version string of the overall model."""
        self._ensure_loaded()
        meta = self._meta.get("overall", {})
        return meta.get("version")

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, row: dict) -> dict[str, float]:
        """
        Predict all 6 scores for a startup.

        Args:
            row: dict with English keys (from CSV or DB row)

        Returns:
            {"overall": 7.2, "tech_maturity": 6.5, ...}
        """
        self._ensure_loaded()

        from scoring.features import extract_features

        x = extract_features(row).reshape(1, -1)

        scores = {}
        for target in TARGET_NAMES:
            if target in self._models:
                raw = float(self._models[target].predict(x)[0])
                scores[target] = round(max(1.0, min(10.0, raw)), 2)
            else:
                scores[target] = 0.0

        return scores

    def predict_batch(self, rows: list[dict]) -> list[dict[str, float]]:
        """Predict scores for multiple startups at once (faster)."""
        self._ensure_loaded()

        from scoring.features import extract_features

        X = np.vstack([extract_features(row).reshape(1, -1) for row in rows])

        all_scores = [{} for _ in rows]
        for target in TARGET_NAMES:
            if target in self._models:
                preds = self._models[target].predict(X)
                for i, raw in enumerate(preds):
                    all_scores[i][target] = round(float(max(1.0, min(10.0, raw))), 2)

        return all_scores

    # ------------------------------------------------------------------
    # SHAP explanations
    # ------------------------------------------------------------------

    def _get_explainer(self, target: str):
        """Lazily create a SHAP TreeExplainer for the given target."""
        if target in self._explainers:
            return self._explainers[target]

        if target not in self._models:
            return None

        try:
            import shap
            explainer = shap.TreeExplainer(self._models[target])
            self._explainers[target] = explainer
            return explainer
        except Exception as e:
            logger.warning("Failed to create SHAP explainer for %s: %s", target, e)
            return None

    def explain(self, row: dict, target: str = "overall", top_n: int = 8) -> Optional[dict]:
        """
        Compute SHAP explanation for a single prediction.

        Returns:
            {
                "predicted_score": 7.2,
                "base_value": 5.1,
                "top_positive": [
                    {"feature": "trl", "contribution": +1.2, "value": 7},
                    ...
                ],
                "top_negative": [
                    {"feature": "revenue_stability", "contribution": -0.3, "value": 0.0},
                    ...
                ],
                "feature_names": [...],
                "shap_values": [...]
            }
        """
        self._ensure_loaded()

        from scoring.features import extract_features

        explainer = self._get_explainer(target)
        if explainer is None:
            return None

        x = extract_features(row).reshape(1, -1)
        shap_values = explainer.shap_values(x)[0]
        base_value = float(explainer.expected_value)

        feature_names = self._feature_names or [f"f{i}" for i in range(len(shap_values))]

        # Sort by absolute contribution
        contributions = []
        for i, (name, sv) in enumerate(zip(feature_names, shap_values)):
            contributions.append({
                "feature": name,
                "contribution": round(float(sv), 4),
                "value": round(float(x[0, i]), 4),
            })

        contributions.sort(key=lambda c: abs(c["contribution"]), reverse=True)

        top_positive = [c for c in contributions if c["contribution"] > 0][:top_n]
        top_negative = [c for c in contributions if c["contribution"] < 0][:top_n]

        predicted = float(self._models[target].predict(x)[0])

        return {
            "predicted_score": round(max(1.0, min(10.0, predicted)), 2),
            "base_value": round(base_value, 2),
            "top_positive": top_positive,
            "top_negative": top_negative,
        }

    def explain_all(self, row: dict, top_n: int = 5) -> dict[str, dict]:
        """SHAP explanation for all 6 targets."""
        results = {}
        for target in TARGET_NAMES:
            exp = self.explain(row, target=target, top_n=top_n)
            if exp:
                results[target] = exp
        return results


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_predictor: Optional[StartupPredictor] = None
_predictor_lock = Lock()


def get_predictor(model_dir: Path | str | None = None) -> StartupPredictor:
    """Get or create the global predictor singleton."""
    global _predictor
    if _predictor is not None:
        return _predictor
    with _predictor_lock:
        if _predictor is not None:
            return _predictor
        _predictor = StartupPredictor(model_dir=model_dir)
        return _predictor
