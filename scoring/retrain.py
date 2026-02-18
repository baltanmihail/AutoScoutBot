"""
Semi-Supervised Retraining Pipeline.

Позволяет дообучать XGBoost модели на стартапах, которых НЕТ в базе Сколково,
при этом данные Сколково всегда остаются "якорем" (ground truth).

Алгоритм:
1. Загружаем оригинальные данные Сколково (5166 стартапов, 100 % верные метки)
2. Загружаем внешние стартапы, для которых парсеры собрали данные
3. Извлекаем 39 признаков для каждого внешнего стартапа
4. Текущая модель даёт "псевдо-метки" (predicted scores)
5. Фильтруем: берём только стартапы, где модель "уверена"
   (prediction variance < порога при дропауте)
6. Объединяем:
   - Сколково = weight 1.0
   - Внешние = weight 0.3-0.7 (зависит от confidence + source reliability)
7. Дообучаем XGBoost с sample_weight
8. Валидируем на held-out 20% Сколково: R² не должен падать
9. Если всё ок → сохраняем новые модели
10. Если метрики упали → откат, используем старые модели

Запуск:
    python -m scoring.retrain
    python -m scoring.retrain --min-external 50 --confidence-threshold 0.8
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)

# Минимальное R² на Сколково после дообучения
# Если ниже -- откатываем модель
MIN_R2_THRESHOLD = 0.80

# Допустимое падение R² по сравнению с baseline (оригинальная модель)
MAX_R2_DROP = 0.03


def load_skolkovo_data(csv_path: str | Path) -> Tuple[np.ndarray, np.ndarray, list, list]:
    """
    Загрузка Сколково (ground truth).

    Returns:
        X_sk      -- (N, 39) матрица признаков
        y_sk      -- dict target_name -> (N,) массив меток
        ids_sk    -- список id стартапов
        feat_names -- список из 39 названий признаков
    """
    from scoring.features import build_feature_matrix, get_feature_names
    from scoring.labeler import label_dataframe

    X, feat_names, ids, y_overall = build_feature_matrix(csv_path)

    labels_df = label_dataframe(csv_path)
    label_map = {r["id"]: r for _, r in labels_df.iterrows()}

    targets = {"overall": y_overall}

    for target_name in ["tech_maturity", "innovation", "market_potential",
                        "team_readiness", "financial_health"]:
        col = f"score_{target_name}"
        y_target = np.array([
            float(label_map.get(sid, {}).get(col, 3.0))
            if sid in label_map and len(label_map[sid]) > 0 else 3.0
            for sid in ids
        ], dtype=np.float32)
        targets[target_name] = y_target

    return X, targets, ids, feat_names


def extract_external_features(external_startups: List[Dict]) -> Tuple[np.ndarray, List[str]]:
    """
    Извлечение 39 признаков для внешних стартапов.

    Args:
        external_startups: список dict-ов с данными парсеров
            Каждый dict должен содержать хотя бы:
            - inn, name
            - revenue_YYYY, profit_YYYY (от BFO)
            - year_founded (от EGRUL)
            - и прочие поля, если доступны

    Returns:
        X_ext   -- (M, 39)
        ids_ext -- список ИНН (как идентификатор)
    """
    from scoring.features import extract_features

    X_list = []
    ids = []

    for startup in external_startups:
        try:
            feats = extract_features(startup)
            X_list.append(feats)
            ids.append(startup.get("inn", startup.get("name", "unknown")))
        except Exception as e:
            logger.warning("Не удалось извлечь признаки для %s: %s",
                           startup.get("name", "?"), e)

    if not X_list:
        return np.empty((0, 39), dtype=np.float32), []

    return np.vstack(X_list), ids


def generate_pseudo_labels(
    X_ext: np.ndarray,
    confidence_threshold: float = 0.8,
    n_bootstrap: int = 10,
) -> Tuple[Dict[str, np.ndarray], np.ndarray]:
    """
    Генерация псевдо-меток для внешних стартапов.

    Используем текущую обученную модель + bootstrap для оценки confidence:
    - Делаем n_bootstrap предсказаний с разными подмножествами деревьев
    - Считаем среднее (= pseudo-label) и стандартное отклонение (= uncertainty)
    - confidence = 1 - normalized_std

    Returns:
        pseudo_labels  -- dict target_name -> (M,) массив псевдо-меток
        confidence     -- (M,) массив confidence [0, 1]
    """
    from scoring.predictor import get_predictor

    predictor = get_predictor()
    if not predictor.is_ready:
        raise RuntimeError("ML модели не загружены. Сначала обучите на Сколково данных.")

    predictor._ensure_loaded()

    target_names = ["overall", "tech_maturity", "innovation",
                    "market_potential", "team_readiness", "financial_health"]

    pseudo_labels = {t: [] for t in target_names}
    all_stds = []

    for i in range(X_ext.shape[0]):
        x = X_ext[i:i+1]
        bootstrap_preds = {t: [] for t in target_names}

        for target in target_names:
            model = predictor._models.get(target)
            if model is None:
                bootstrap_preds[target] = [3.0] * n_bootstrap
                continue

            n_trees = model.get_booster().num_boosted_rounds()
            for b in range(n_bootstrap):
                np.random.seed(42 + b)
                tree_subset = max(1, int(n_trees * np.random.uniform(0.7, 1.0)))
                raw = float(model.predict(x, iteration_range=(0, tree_subset))[0])
                bootstrap_preds[target].append(max(1.0, min(10.0, raw)))

        stds = []
        for target in target_names:
            preds = bootstrap_preds[target]
            mean_pred = np.mean(preds)
            std_pred = np.std(preds)
            pseudo_labels[target].append(mean_pred)
            stds.append(std_pred)

        avg_std = np.mean(stds)
        all_stds.append(avg_std)

    max_std = max(all_stds) if all_stds else 1.0
    if max_std == 0:
        max_std = 1.0

    confidence = np.array([1.0 - (s / max_std) for s in all_stds], dtype=np.float32)
    confidence = np.clip(confidence, 0.0, 1.0)

    for t in target_names:
        pseudo_labels[t] = np.array(pseudo_labels[t], dtype=np.float32)

    return pseudo_labels, confidence


def compute_sample_weights(
    n_skolkovo: int,
    n_external: int,
    confidence: np.ndarray,
    source_reliability: Optional[np.ndarray] = None,
    skolkovo_weight: float = 1.0,
    external_base_weight: float = 0.5,
) -> np.ndarray:
    """
    Вычисление весов для каждого сэмпла.

    Сколково стартапы всегда получают weight = 1.0.
    Внешние стартапы получают weight = external_base_weight * confidence * source_reliability.

    Returns:
        weights -- (n_skolkovo + n_external,)
    """
    sk_weights = np.full(n_skolkovo, skolkovo_weight, dtype=np.float32)

    ext_weights = np.full(n_external, external_base_weight, dtype=np.float32)
    ext_weights *= confidence

    if source_reliability is not None:
        ext_weights *= source_reliability

    ext_weights = np.clip(ext_weights, 0.1, 0.7)

    return np.concatenate([sk_weights, ext_weights])


def retrain_with_external(
    csv_path: str | Path,
    external_startups: List[Dict],
    confidence_threshold: float = 0.8,
    min_external: int = 10,
    model_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict:
    """
    Основная функция дообучения.

    Args:
        csv_path: путь к SkolkovoStartups.csv
        external_startups: список dict-ов с данными от парсеров
        confidence_threshold: порог уверенности (0-1)
        min_external: минимум внешних стартапов для запуска
        model_dir: директория для сохранения моделей
        dry_run: если True -- не сохраняем, только считаем метрики

    Returns:
        dict с результатами:
        {
            "status": "success" | "skipped" | "rollback",
            "reason": str,
            "n_external_used": int,
            "metrics_before": {target: {r2, mae}},
            "metrics_after": {target: {r2, mae}},
        }
    """
    import xgboost as xgb
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error, r2_score

    if model_dir is None:
        model_dir = ROOT / "scoring" / "models"

    result = {
        "timestamp": dt.datetime.now().isoformat(),
        "status": "skipped",
        "reason": "",
        "n_skolkovo": 0,
        "n_external_total": 0,
        "n_external_used": 0,
        "metrics_before": {},
        "metrics_after": {},
    }

    # --- 1. Загрузка Сколково ---
    logger.info("=== Шаг 1: Загрузка данных Сколково ===")
    X_sk, targets_sk, ids_sk, feat_names = load_skolkovo_data(csv_path)
    result["n_skolkovo"] = X_sk.shape[0]
    logger.info("Загружено %d стартапов Сколково, %d признаков", X_sk.shape[0], X_sk.shape[1])

    # --- 2. Извлечение признаков из внешних стартапов ---
    logger.info("=== Шаг 2: Извлечение признаков из внешних данных ===")
    X_ext, ids_ext = extract_external_features(external_startups)
    result["n_external_total"] = X_ext.shape[0]

    if X_ext.shape[0] < min_external:
        result["reason"] = (
            f"Недостаточно внешних стартапов: {X_ext.shape[0]} < {min_external}. "
            "Дообучение отложено."
        )
        logger.info(result["reason"])
        return result

    logger.info("Извлечены признаки для %d внешних стартапов", X_ext.shape[0])

    # --- 3. Генерация псевдо-меток ---
    logger.info("=== Шаг 3: Генерация псевдо-меток (bootstrap) ===")
    pseudo_labels, confidence = generate_pseudo_labels(X_ext, confidence_threshold)

    confident_mask = confidence >= confidence_threshold
    n_confident = int(confident_mask.sum())
    result["n_external_used"] = n_confident

    if n_confident < min_external:
        result["reason"] = (
            f"Мало уверенных псевдо-меток: {n_confident} < {min_external} "
            f"(порог confidence={confidence_threshold}). Дообучение отложено."
        )
        logger.info(result["reason"])
        return result

    logger.info(
        "Уверенных стартапов: %d из %d (порог %.2f)",
        n_confident, X_ext.shape[0], confidence_threshold
    )

    X_ext_conf = X_ext[confident_mask]
    confidence_conf = confidence[confident_mask]

    # --- 4. Baseline метрики (текущие модели на hold-out Сколково) ---
    logger.info("=== Шаг 4: Baseline метрики ===")

    X_sk_train, X_sk_test, idx_train, idx_test = train_test_split(
        X_sk, np.arange(X_sk.shape[0]),
        test_size=0.2, random_state=42
    )

    from scoring.predictor import get_predictor
    predictor = get_predictor()
    predictor._ensure_loaded()

    for target_name in targets_sk:
        y_test = targets_sk[target_name][idx_test]
        if target_name in predictor._models:
            y_pred = predictor._models[target_name].predict(X_sk_test)
            y_pred = np.clip(y_pred, 1.0, 10.0)
            baseline_r2 = float(r2_score(y_test, y_pred))
            baseline_mae = float(mean_absolute_error(y_test, y_pred))
        else:
            baseline_r2 = 0.0
            baseline_mae = 999.0

        result["metrics_before"][target_name] = {
            "r2": round(baseline_r2, 4),
            "mae": round(baseline_mae, 4),
        }
        logger.info("  %s: R²=%.4f, MAE=%.4f", target_name, baseline_r2, baseline_mae)

    # --- 5. Объединение данных и дообучение ---
    logger.info("=== Шаг 5: Дообучение (Skolkovo + %d внешних) ===", n_confident)

    X_combined_train = np.vstack([X_sk_train, X_ext_conf])
    sample_weights = compute_sample_weights(
        n_skolkovo=X_sk_train.shape[0],
        n_external=X_ext_conf.shape[0],
        confidence=confidence_conf,
    )

    new_models = {}
    for target_name in targets_sk:
        y_sk_train = targets_sk[target_name][idx_train]
        y_ext_conf = pseudo_labels[target_name][confident_mask]
        y_combined = np.concatenate([y_sk_train, y_ext_conf])

        model = xgb.XGBRegressor(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_combined_train, y_combined, sample_weight=sample_weights, verbose=False)
        new_models[target_name] = model

    # --- 6. Валидация на held-out Сколково ---
    logger.info("=== Шаг 6: Валидация на held-out Сколково ===")
    rollback_needed = False

    for target_name in targets_sk:
        y_test = targets_sk[target_name][idx_test]
        y_pred = new_models[target_name].predict(X_sk_test)
        y_pred = np.clip(y_pred, 1.0, 10.0)

        new_r2 = float(r2_score(y_test, y_pred))
        new_mae = float(mean_absolute_error(y_test, y_pred))

        result["metrics_after"][target_name] = {
            "r2": round(new_r2, 4),
            "mae": round(new_mae, 4),
        }

        baseline_r2 = result["metrics_before"][target_name]["r2"]
        r2_drop = baseline_r2 - new_r2

        logger.info(
            "  %s: R²=%.4f (было %.4f, %+.4f), MAE=%.4f",
            target_name, new_r2, baseline_r2, -r2_drop, new_mae
        )

        if new_r2 < MIN_R2_THRESHOLD:
            logger.warning(
                "  ❌ R² для %s ниже порога (%.4f < %.4f)",
                target_name, new_r2, MIN_R2_THRESHOLD
            )
            rollback_needed = True

        if r2_drop > MAX_R2_DROP:
            logger.warning(
                "  ❌ R² для %s упал более чем на %.4f (%.4f)",
                target_name, MAX_R2_DROP, r2_drop
            )
            rollback_needed = True

    if rollback_needed:
        result["status"] = "rollback"
        result["reason"] = (
            "Метрики на Сколково упали ниже допустимого порога. "
            "Модели НЕ обновлены. Попробуйте увеличить confidence_threshold."
        )
        logger.warning(result["reason"])
        return result

    # --- 7. Если всё ок -- дообучаем на ПОЛНЫХ данных и сохраняем ---
    if dry_run:
        result["status"] = "dry_run"
        result["reason"] = "Dry run: модели не сохранены, метрики рассчитаны."
        logger.info(result["reason"])
        return result

    logger.info("=== Шаг 7: Финальное обучение на полных данных ===")
    X_full = np.vstack([X_sk, X_ext_conf])
    full_weights = compute_sample_weights(
        n_skolkovo=X_sk.shape[0],
        n_external=X_ext_conf.shape[0],
        confidence=confidence_conf,
    )

    from scoring.train import save_model as _save, feature_importance_report

    for target_name in targets_sk:
        y_sk_full = targets_sk[target_name]
        y_ext_conf = pseudo_labels[target_name][confident_mask]
        y_full = np.concatenate([y_sk_full, y_ext_conf])

        final_model = xgb.XGBRegressor(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=-1,
        )
        final_model.fit(X_full, y_full, sample_weight=full_weights, verbose=False)

        importance = feature_importance_report(final_model, feat_names)
        cv_metrics = result["metrics_after"][target_name]
        cv_metrics["n_samples"] = int(X_full.shape[0])
        cv_metrics["n_skolkovo"] = int(X_sk.shape[0])
        cv_metrics["n_external"] = int(X_ext_conf.shape[0])

        target_dir = model_dir / target_name
        _save(
            final_model, cv_metrics, feat_names, importance,
            engine="xgboost", model_dir=target_dir,
        )
        logger.info("  Модель '%s' сохранена в %s", target_name, target_dir)

    # Сохраняем лог дообучения
    retrain_log_path = model_dir / "retrain_log.json"
    logs = []
    if retrain_log_path.exists():
        try:
            logs = json.loads(retrain_log_path.read_text(encoding="utf-8"))
        except Exception:
            logs = []
    logs.append(result)
    retrain_log_path.write_text(
        json.dumps(logs, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    result["status"] = "success"
    result["reason"] = (
        f"Модели успешно дообучены на {X_sk.shape[0]} Сколково + "
        f"{n_confident} внешних стартапах."
    )
    logger.info(result["reason"])

    return result


def prepare_external_from_db() -> List[Dict]:
    """
    Загрузка внешних стартапов из БД (SQLite или PostgreSQL).

    Конвертирует данные raw_external_data в формат,
    совместимый с extract_features().
    """
    import sqlite3

    db_path = ROOT / "users.db"
    if not db_path.exists():
        logger.info("БД users.db не найдена -- нет внешних стартапов")
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='external_startups'")
        if not cursor.fetchone():
            logger.info("Таблица external_startups не существует")
            return []

        cursor.execute("SELECT * FROM external_startups")
        rows = cursor.fetchall()
    except Exception as e:
        logger.warning("Ошибка при чтении external_startups: %s", e)
        return []
    finally:
        conn.close()

    startups = []
    for row in rows:
        row_dict = dict(row)
        features_json = row_dict.get("features_json", "{}")
        try:
            features = json.loads(features_json)
        except Exception:
            features = {}

        startup = {
            "inn": row_dict.get("inn", ""),
            "name": row_dict.get("name", ""),
            "full_legal_name": row_dict.get("full_legal_name", ""),
            "year_founded": str(row_dict.get("registration_date", ""))[:4] if row_dict.get("registration_date") else "",
            "status": row_dict.get("status_egrul", ""),
            "region": row_dict.get("region", ""),
        }
        startup.update(features)
        startups.append(startup)

    logger.info("Загружено %d внешних стартапов из БД", len(startups))
    return startups


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Дообучение ML моделей на внешних стартапах (Semi-Supervised)"
    )
    parser.add_argument(
        "--csv", default=str(ROOT / "SkolkovoStartups.csv"),
        help="Путь к SkolkovoStartups.csv"
    )
    parser.add_argument(
        "--model-dir", default=str(ROOT / "scoring" / "models"),
        help="Директория моделей"
    )
    parser.add_argument(
        "--confidence-threshold", type=float, default=0.8,
        help="Порог уверенности для псевдо-меток (0-1)"
    )
    parser.add_argument(
        "--min-external", type=int, default=10,
        help="Минимум внешних стартапов для запуска"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Только рассчитать метрики, не сохранять модели"
    )
    args = parser.parse_args()

    external_startups = prepare_external_from_db()

    if not external_startups:
        print("\n⚠️  Нет внешних стартапов для дообучения.")
        print("Используйте команду /check в боте для сбора данных,")
        print("или добавьте стартапы через парсеры.")
        return

    result = retrain_with_external(
        csv_path=args.csv,
        external_startups=external_startups,
        confidence_threshold=args.confidence_threshold,
        min_external=args.min_external,
        model_dir=Path(args.model_dir),
        dry_run=args.dry_run,
    )

    print(f"\n{'='*60}")
    print(f"Результат: {result['status']}")
    print(f"Причина: {result['reason']}")
    print(f"Сколково: {result['n_skolkovo']}")
    print(f"Внешних (всего): {result['n_external_total']}")
    print(f"Внешних (использовано): {result['n_external_used']}")

    if result['metrics_before']:
        print(f"\nМетрики ДО:")
        for t, m in result['metrics_before'].items():
            print(f"  {t}: R²={m['r2']:.4f}, MAE={m['mae']:.4f}")

    if result['metrics_after']:
        print(f"\nМетрики ПОСЛЕ:")
        for t, m in result['metrics_after'].items():
            print(f"  {t}: R²={m['r2']:.4f}, MAE={m['mae']:.4f}")


if __name__ == "__main__":
    main()
