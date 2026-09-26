"""Model architectures and training pipelines for Tram Ridership Prediction.

Supports:
- CatBoost (with GPU acceleration and auto-CPU fallback)
- LightGBM (with GPU acceleration)
- HistGradientBoosting (Sklearn, pure CPU)
- Ridge (Sklearn linear baseline)
- Baseline (Pure historical profile)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ml.training.tram.evaluation import compute_wape_metrics
from ml.training.tram.features import (
    ACTIVE_ROUTES,
    CATEGORICAL_FEATURES,
    FEATURE_COLS,
    ROUTE_CAT_FEATURES,
    ROUTE_FEATURE_COLS,
)


def train_validation_models(
    train_feat: pd.DataFrame,
    val_feat: pd.DataFrame,
    base_col: str,
    model_type: str = "catboost",
    iterations: int = 2000,
    learning_rate: float = 0.04,
    depth: int = 6,
    use_gpu: bool = True,
    use_residual: bool = True,
    per_route: bool = True,
) -> tuple[dict[int, Any] | Any, np.ndarray, dict]:
    """Train models on train_feat, evaluate on val_feat, and return fitted models and predictions."""
    base_train = train_feat[base_col].values
    base_val = val_feat[base_col].values

    y_train = train_feat["boardings"].values
    y_val = val_feat["boardings"].values

    if use_residual:
        print("Using Residual Learning (target = boardings - base_profile)...")
        y_train_fit = y_train - base_train
        y_val_fit = y_val - base_val
    else:
        y_train_fit = y_train
        y_val_fit = y_val

    active_features = [c for c in FEATURE_COLS if c in train_feat.columns]
    active_route_features = [c for c in active_features if c != "route"]

    X_train = train_feat[active_features]
    X_val = val_feat[active_features]

    val_preds = np.zeros(len(val_feat), dtype=float)
    route_models: dict[int, Any] = {}
    single_model: Any = None

    if model_type == "baseline":
        print("Using historical seasonal profile baseline (pure numpy/pandas)...")
        val_preds = base_val.copy()

    elif model_type == "catboost":
        try:
            from catboost import CatBoostRegressor
        except ImportError as err:
            raise ImportError("Please install catboost: pip install catboost") from err

        cb_params: dict[str, Any] = {
            "loss_function": "MAE",
            "eval_metric": "MAE",
            "iterations": iterations,
            "learning_rate": learning_rate,
            "depth": depth,
            "random_seed": 42,
            "verbose": 0 if per_route else 200,
            "cat_features": ROUTE_CAT_FEATURES if per_route else CATEGORICAL_FEATURES,
        }
        if use_gpu:
            cb_params["task_type"] = "GPU"
            cb_params["metric_period"] = 5
        else:
            cb_params["task_type"] = "CPU"
            cb_params["thread_count"] = -1

        if per_route:
            print("Training 9 specialized per-route CatBoost models...")
            for r in ACTIVE_ROUTES:
                mask_tr = (train_feat["route"] == r) & (train_feat["is_summer"] == 0)
                mask_val = val_feat["route"] == r
                X_tr_r = train_feat.loc[mask_tr, active_route_features]
                y_tr_r = y_train_fit[mask_tr]
                X_val_r = val_feat.loc[mask_val, active_route_features]
                y_val_r = y_val_fit[mask_val]

                m_r = CatBoostRegressor(**cb_params)
                try:
                    m_r.fit(
                        X_tr_r,
                        y_tr_r,
                        eval_set=(X_val_r, y_val_r),
                        early_stopping_rounds=150,
                        verbose=0,
                    )
                except Exception:
                    cb_params_cpu = cb_params.copy()
                    cb_params_cpu["task_type"] = "CPU"
                    cb_params_cpu["thread_count"] = -1
                    m_r = CatBoostRegressor(**cb_params_cpu)
                    m_r.fit(
                        X_tr_r,
                        y_tr_r,
                        eval_set=(X_val_r, y_val_r),
                        early_stopping_rounds=150,
                        verbose=0,
                    )

                raw_preds_r = m_r.predict(X_val_r)
                if use_residual:
                    val_preds[mask_val] = base_val[mask_val] + raw_preds_r
                else:
                    val_preds[mask_val] = raw_preds_r
                route_models[r] = m_r
                r_wape = compute_wape_metrics(y_val[mask_val], val_preds[mask_val])
                print(
                    f"  Route {r:2d} finished: best_iter={m_r.get_best_iteration():4d}, "
                    f"WAPE={r_wape['wape']:.4f}, WAPE-score={r_wape['wape_score']:.4f}"
                )
        else:
            try:
                single_model = CatBoostRegressor(**cb_params)
                single_model.fit(
                    X_train,
                    y_train_fit,
                    eval_set=(X_val, y_val_fit),
                    early_stopping_rounds=100,
                    verbose=200,
                )
            except Exception:
                cb_params["task_type"] = "CPU"
                cb_params["thread_count"] = -1
                single_model = CatBoostRegressor(**cb_params)
                single_model.fit(
                    X_train,
                    y_train_fit,
                    eval_set=(X_val, y_val_fit),
                    early_stopping_rounds=100,
                    verbose=200,
                )
            raw_val_preds = single_model.predict(X_val)
            val_preds = base_val + raw_val_preds if use_residual else raw_val_preds

    elif model_type == "lightgbm":
        try:
            import lightgbm as lgb
        except ImportError as err:
            raise ImportError("Please install lightgbm: pip install lightgbm") from err

        lgb_params: dict[str, Any] = {
            "objective": "mae",
            "metric": "mae",
            "learning_rate": learning_rate,
            "num_leaves": 2**depth - 1,
            "random_state": 42,
            "verbose": -1,
        }
        if use_gpu:
            lgb_params["device"] = "gpu"

        if per_route:
            print("Training 9 specialized per-route LightGBM models...")
            for r in ACTIVE_ROUTES:
                mask_tr = (train_feat["route"] == r) & (train_feat["is_summer"] == 0)
                mask_val = val_feat["route"] == r
                X_tr_r = train_feat.loc[mask_tr, ROUTE_FEATURE_COLS]
                y_tr_r = y_train_fit[mask_tr]
                X_val_r = val_feat.loc[mask_val, ROUTE_FEATURE_COLS]
                y_val_r = y_val_fit[mask_val]

                dtrain = lgb.Dataset(X_tr_r, label=y_tr_r, categorical_feature=ROUTE_CAT_FEATURES)
                dval = lgb.Dataset(
                    X_val_r, label=y_val_r, reference=dtrain, categorical_feature=ROUTE_CAT_FEATURES
                )
                m_r = lgb.train(
                    lgb_params,
                    dtrain,
                    num_boost_round=iterations,
                    valid_sets=[dtrain, dval],
                    callbacks=[lgb.early_stopping(stopping_rounds=100, verbose=False)],
                )
                raw_preds_r = m_r.predict(X_val_r)
                val_preds[mask_val] = (
                    (base_val[mask_val] + raw_preds_r) if use_residual else raw_preds_r
                )
                route_models[r] = m_r
        else:
            dtrain = lgb.Dataset(
                X_train, label=y_train_fit, categorical_feature=CATEGORICAL_FEATURES
            )
            dval = lgb.Dataset(
                X_val, label=y_val_fit, reference=dtrain, categorical_feature=CATEGORICAL_FEATURES
            )
            single_model = lgb.train(
                lgb_params,
                dtrain,
                num_boost_round=iterations,
                valid_sets=[dtrain, dval],
                callbacks=[lgb.early_stopping(stopping_rounds=100), lgb.log_evaluation(period=200)],
            )
            raw_val_preds = single_model.predict(X_val)
            val_preds = base_val + raw_val_preds if use_residual else raw_val_preds

    elif model_type == "histgradient":
        from sklearn.ensemble import HistGradientBoostingRegressor

        print("Training Sklearn HistGradientBoostingRegressor with absolute_error (MAE) loss...")
        cat_indices = [FEATURE_COLS.index(c) for c in CATEGORICAL_FEATURES]
        single_model = HistGradientBoostingRegressor(
            loss="absolute_error",
            max_iter=min(iterations, 400),
            learning_rate=learning_rate,
            max_depth=depth,
            categorical_features=cat_indices,
            random_state=42,
        )
        single_model.fit(X_train, y_train_fit)
        raw_val_preds = single_model.predict(X_val)
        val_preds = base_val + raw_val_preds if use_residual else raw_val_preds

    # Clip and zero-force Route 5
    val_preds = np.clip(np.round(val_preds), 0, None)
    val_preds[val_feat["route"].values == 5] = 0

    return (route_models if per_route else single_model), val_preds, {}


def fit_final_and_predict(
    full_train_feat: pd.DataFrame,
    sub_feat: pd.DataFrame,
    base_col: str,
    val_models: dict[int, Any] | Any,
    model_type: str = "catboost",
    iterations: int = 2000,
    learning_rate: float = 0.04,
    depth: int = 6,
    use_gpu: bool = True,
    use_residual: bool = True,
    per_route: bool = True,
) -> np.ndarray:
    """Refit on full Jan-Oct data and generate predictions for Nov-Dec test grid."""
    base_full = full_train_feat[base_col].values
    base_sub = sub_feat[base_col].values

    y_full = full_train_feat["boardings"].values
    y_full_fit = y_full - base_full if use_residual else y_full

    active_features = [c for c in FEATURE_COLS if c in full_train_feat.columns]
    active_route_features = [c for c in active_features if c != "route"]

    X_full = full_train_feat[active_features]
    X_sub = sub_feat[active_features]

    sub_preds = np.zeros(len(sub_feat), dtype=float)

    if model_type == "baseline":
        print("Using historical seasonal profile baseline for final submission...")
        sub_preds = base_sub.copy()

    elif per_route and model_type == "catboost":
        from catboost import CatBoostRegressor

        print("Fitting final per-route CatBoost models on full Jan-Oct history...")
        cb_params: dict[str, Any] = {
            "loss_function": "MAE",
            "eval_metric": "MAE",
            "learning_rate": learning_rate,
            "depth": depth,
            "random_seed": 42,
            "verbose": 0,
            "cat_features": ROUTE_CAT_FEATURES,
        }
        if use_gpu:
            cb_params["task_type"] = "GPU"
        else:
            cb_params["task_type"] = "CPU"
            cb_params["thread_count"] = -1

        for r in ACTIVE_ROUTES:
            mask_full = (full_train_feat["route"] == r) & (full_train_feat["is_summer"] == 0)
            mask_sub = sub_feat["route"] == r
            X_full_r = full_train_feat.loc[mask_full, active_route_features]
            y_full_r = y_full_fit[mask_full]
            X_sub_r = sub_feat.loc[mask_sub, active_route_features]

            best_iter = val_models[r].get_best_iteration() or iterations
            final_cb_params = cb_params.copy()
            final_cb_params["iterations"] = max(best_iter, 300)

            final_m_r = CatBoostRegressor(**final_cb_params)
            try:
                final_m_r.fit(X_full_r, y_full_r, verbose=0)
            except Exception:
                final_cb_params["task_type"] = "CPU"
                final_cb_params["thread_count"] = -1
                final_m_r = CatBoostRegressor(**final_cb_params)
                final_m_r.fit(X_full_r, y_full_r, verbose=0)

            raw_sub_r = final_m_r.predict(X_sub_r)
            sub_pred_r = (base_sub[mask_sub] + raw_sub_r) if use_residual else raw_sub_r
            sub_preds[mask_sub] = sub_pred_r

    elif per_route and model_type == "lightgbm":
        import lightgbm as lgb

        print("Fitting final per-route LightGBM models on full Jan-Oct history...")
        lgb_params = {
            "objective": "mae",
            "metric": "mae",
            "learning_rate": learning_rate,
            "num_leaves": 2**depth - 1,
            "random_state": 42,
            "verbose": -1,
        }
        for r in ACTIVE_ROUTES:
            mask_full = (full_train_feat["route"] == r) & (full_train_feat["is_summer"] == 0)
            mask_sub = sub_feat["route"] == r
            X_full_r = full_train_feat.loc[mask_full, ROUTE_FEATURE_COLS]
            y_full_r = y_full_fit[mask_full]
            X_sub_r = sub_feat.loc[mask_sub, ROUTE_FEATURE_COLS]

            best_iter = val_models[r].best_iteration or iterations
            d_full_r = lgb.Dataset(X_full_r, label=y_full_r, categorical_feature=ROUTE_CAT_FEATURES)
            final_m_r = lgb.train(lgb_params, d_full_r, num_boost_round=best_iter)
            raw_sub_r = final_m_r.predict(X_sub_r)
            sub_preds[mask_sub] = (base_sub[mask_sub] + raw_sub_r) if use_residual else raw_sub_r

    elif model_type == "catboost":
        from catboost import CatBoostRegressor

        final_iterations = val_models.get_best_iteration() or iterations
        print(f"Training final CatBoost model on full data ({final_iterations} iterations)...")
        cb_params = {
            "loss_function": "MAE",
            "eval_metric": "MAE",
            "learning_rate": learning_rate,
            "depth": depth,
            "random_seed": 42,
            "verbose": 200,
            "cat_features": CATEGORICAL_FEATURES,
            "iterations": max(final_iterations, 300),
            "task_type": "GPU" if use_gpu else "CPU",
        }
        try:
            final_model = CatBoostRegressor(**cb_params)
            final_model.fit(X_full, y_full_fit, verbose=200)
        except Exception:
            cb_params["task_type"] = "CPU"
            cb_params["thread_count"] = -1
            final_model = CatBoostRegressor(**cb_params)
            final_model.fit(X_full, y_full_fit, verbose=200)

        raw_sub = final_model.predict(X_sub)
        sub_preds = (base_sub + raw_sub) if use_residual else raw_sub

    elif model_type == "histgradient":
        from sklearn.ensemble import HistGradientBoostingRegressor

        print("Training final Sklearn HistGradientBoostingRegressor on full data...")
        cat_indices = [FEATURE_COLS.index(c) for c in CATEGORICAL_FEATURES]
        final_model = HistGradientBoostingRegressor(
            loss="absolute_error",
            max_iter=min(iterations, 400),
            learning_rate=learning_rate,
            max_depth=depth,
            categorical_features=cat_indices,
            random_state=42,
        )
        final_model.fit(X_full, y_full_fit)
        raw_sub = final_model.predict(X_sub)
        sub_preds = (base_sub + raw_sub) if use_residual else raw_sub

    sub_preds = np.clip(np.round(sub_preds), 0, None)
    sub_preds[sub_feat["route"].values == 5] = 0
    return sub_preds
