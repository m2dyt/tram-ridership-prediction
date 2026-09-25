"""End-to-end training and inference pipeline for Tram Ridership Prediction.

Supports NVIDIA GPU acceleration via CatBoost (task_type='GPU') and LightGBM (device='gpu').
Automatically falls back to multi-threaded CPU if GPU is not available.

Features:
- Full Cartesian grid generation (dates x 24 hours x 10 routes)
- Zero-filling for nocturnal / missing hours (fixing the missing zero bias)
- Leak-free historical seasonal profiles (route x dow x hour)
- Russian 2025 calendar: holidays, pre-holidays, transferred weekends
- Route 5 special handling (guaranteed 0)
- Validation on Sept-Oct 2025 fold with exact WAPE and WAPE-score calculation
- Full refit on Jan-Oct 2025 and submission generation for Nov-Dec 2025
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Russian 2025 official non-working holidays and transferred days
HOLIDAYS_2025 = {
    # New Year holidays
    "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04",
    "2025-01-05", "2025-01-06", "2025-01-07", "2025-01-08",
    # Defender of Fatherland
    "2025-02-22", "2025-02-23",
    # International Women's Day
    "2025-03-08", "2025-03-09",
    # Spring and Labor
    "2025-05-01", "2025-05-02", "2025-05-03", "2025-05-04",
    # Victory Day
    "2025-05-08", "2025-05-09", "2025-05-10", "2025-05-11",
    # Russia Day
    "2025-06-12", "2025-06-13", "2025-06-14", "2025-06-15",
    # Unity Day
    "2025-11-02", "2025-11-03", "2025-11-04",
    # New Year Eve
    "2025-12-31",
}

# Pre-holidays (reduced working hours)
PRE_HOLIDAYS_2025 = {
    "2025-03-07",
    "2025-04-30",
    "2025-06-11",
    "2025-11-01",  # Saturday workday before Unity Day
}

ALL_ROUTES = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]


def generate_full_grid(start_date: str, end_date: str, routes: list[int] = ALL_ROUTES) -> pd.DataFrame:
    """Generate a complete Cartesian grid of (date, hour, route) with all 24 hours."""
    dates = pd.date_range(start=start_date, end=end_date, freq="D").strftime("%Y-%m-%d")
    hours = list(range(24))

    grid = pd.MultiIndex.from_product(
        [dates, hours, routes],
        names=["date", "hour", "route"],
    ).to_frame().reset_index(drop=True)

    grid["route"] = grid["route"].astype(int)
    grid["hour"] = grid["hour"].astype(int)
    return grid


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add rich temporal, calendar, and Russian holiday features."""
    df = df.copy()
    dt = pd.to_datetime(df["date"])

    df["dayofweek"] = dt.dt.dayofweek
    df["month"] = dt.dt.month
    df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)

    df["is_holiday"] = df["date"].isin(HOLIDAYS_2025).astype(int)
    df["is_preholiday"] = df["date"].isin(PRE_HOLIDAYS_2025).astype(int)
    df["is_workday"] = ((df["is_weekend"] == 0) & (df["is_holiday"] == 0)).astype(int)
    df["is_day_off"] = ((df["is_weekend"] == 1) | (df["is_holiday"] == 1)).astype(int)
    df["is_summer"] = df["month"].isin([6, 7, 8]).astype(int)

    # In transport systems, public holidays operate on Sunday schedule (dow=6),
    # and working Saturdays (pre-holidays) operate on Friday schedule (dow=4).
    df["dow_effective"] = df["dayofweek"]
    df.loc[df["is_holiday"] == 1, "dow_effective"] = 6
    df.loc[(df["is_preholiday"] == 1) & (df["is_weekend"] == 1), "dow_effective"] = 4

    # Cyclical encodings (safe for tree extrapolation)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["dow_effective"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["dow_effective"] / 7)

    # Peak hour indicators
    df["is_morning_peak"] = df["hour"].isin([7, 8, 9]).astype(int) * df["is_workday"]
    df["is_evening_peak"] = df["hour"].isin([17, 18, 19]).astype(int) * df["is_workday"]
    df["is_night"] = df["hour"].isin([1, 2, 3, 4]).astype(int)

    return df


def calculate_historical_profiles(train_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Calculate historical passenger profiles on train data only (no data leakage)."""
    # 1. Route x dow_effective x Hour profile (holidays automatically use Sunday schedule)
    prof_route_dow_hour = (
        train_df.groupby(["route", "dow_effective", "hour"])["boardings"]
        .agg(["mean", "median", "std"])
        .reset_index()
        .rename(
            columns={
                "mean": "hist_mean_route_dow_hour",
                "median": "hist_median_route_dow_hour",
                "std": "hist_std_route_dow_hour",
            }
        )
    )

    # 2. Non-summer profile (normal work period: excludes June, July, August vacation slump)
    # This gives a much more accurate baseline for autumn (Sep-Oct) and winter (Nov-Dec).
    nonsummer_df = train_df[train_df["is_summer"] == 0]
    if len(nonsummer_df) > 0:
        prof_route_dow_hour_nonsummer = (
            nonsummer_df.groupby(["route", "dow_effective", "hour"])["boardings"]
            .median()
            .reset_index()
            .rename(columns={"boardings": "hist_median_nonsummer_route_dow_hour"})
        )
    else:
        prof_route_dow_hour_nonsummer = prof_route_dow_hour[["route", "dow_effective", "hour", "hist_median_route_dow_hour"]].rename(
            columns={"hist_median_route_dow_hour": "hist_median_nonsummer_route_dow_hour"}
        )

    # 3. Route x IsDayOff x Hour profile
    prof_route_dayoff_hour = (
        train_df.groupby(["route", "is_day_off", "hour"])["boardings"]
        .agg(["mean", "median"])
        .reset_index()
        .rename(
            columns={
                "mean": "hist_mean_route_dayoff_hour",
                "median": "hist_median_route_dayoff_hour",
            }
        )
    )

    # 4. Route x Hour overall profile
    prof_route_hour = (
        train_df.groupby(["route", "hour"])["boardings"]
        .mean()
        .reset_index()
        .rename(columns={"boardings": "hist_mean_route_hour"})
    )

    # 5. Route overall volume
    prof_route = (
        train_df.groupby("route")["boardings"]
        .mean()
        .reset_index()
        .rename(columns={"boardings": "hist_mean_route"})
    )

    return {
        "prof_route_dow_hour": prof_route_dow_hour,
        "prof_route_dow_hour_nonsummer": prof_route_dow_hour_nonsummer,
        "prof_route_dayoff_hour": prof_route_dayoff_hour,
        "prof_route_hour": prof_route_hour,
        "prof_route": prof_route,
    }


def attach_historical_profiles(df: pd.DataFrame, profiles: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Attach computed historical profiles to any dataset (train, val, or test)."""
    df = df.copy()

    df = df.merge(profiles["prof_route_dow_hour"], on=["route", "dow_effective", "hour"], how="left")
    df = df.merge(profiles["prof_route_dow_hour_nonsummer"], on=["route", "dow_effective", "hour"], how="left")
    df = df.merge(profiles["prof_route_dayoff_hour"], on=["route", "is_day_off", "hour"], how="left")
    df = df.merge(profiles["prof_route_hour"], on=["route", "hour"], how="left")
    df = df.merge(profiles["prof_route"], on=["route"], how="left")

    # For route 5 (or unknown combinations), fill NaNs with 0
    stat_cols = [
        "hist_mean_route_dow_hour",
        "hist_median_route_dow_hour",
        "hist_median_nonsummer_route_dow_hour",
        "hist_std_route_dow_hour",
        "hist_mean_route_dayoff_hour",
        "hist_median_route_dayoff_hour",
        "hist_mean_route_hour",
        "hist_mean_route",
    ]
    for col in stat_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    return df


def compute_wape_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute WAPE and official competition WAPE-score."""
    abs_errors = np.abs(y_true - y_pred)
    sum_y = np.sum(y_true)
    if sum_y > 0:
        wape = float(np.sum(abs_errors) / sum_y)
    else:
        wape = 0.0
    wape_score = max(0.0, 1.0 - wape)
    mae = float(np.mean(abs_errors))
    return {
        "wape": wape,
        "wape_score": wape_score,
        "mae": mae,
    }


def build_feature_matrix(
    data_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load raw labels, generate full grids with missing zeros, and split into train, val, and submission test."""
    train_lbl_path = data_dir / "labels" / "labels_day_train.csv"
    test_lbl_path = data_dir / "labels" / "labels_day_test.csv"

    if not train_lbl_path.is_file() or not test_lbl_path.is_file():
        raise FileNotFoundError(f"Missing label files in {data_dir / 'labels'}")

    print("Loading labels...")
    df_train_lbl = pd.read_csv(train_lbl_path, sep=";")
    df_test_lbl = pd.read_csv(test_lbl_path, sep=";")

    # 1. Full grid for Train: 2025-01-01 to 2025-08-31
    print("Generating complete grid for Train (Jan-Aug 2025)...")
    grid_train = generate_full_grid("2025-01-01", "2025-08-31")
    grid_train = grid_train.merge(df_train_lbl, on=["route", "date", "hour"], how="left")
    grid_train["boardings"] = grid_train["boardings"].fillna(0.0)

    # 2. Full grid for Validation: 2025-09-01 to 2025-10-31
    print("Generating complete grid for Validation (Sep-Oct 2025)...")
    grid_val = generate_full_grid("2025-09-01", "2025-10-31")
    grid_val = grid_val.merge(df_test_lbl, on=["route", "date", "hour"], how="left")
    grid_val["boardings"] = grid_val["boardings"].fillna(0.0)

    # 3. Full grid for Submission: 2025-11-01 to 2025-12-31
    print("Generating complete grid for Submission (Nov-Dec 2025)...")
    grid_sub = generate_full_grid("2025-11-01", "2025-12-31")
    grid_sub["boardings"] = np.nan

    # Add calendar features
    grid_train = add_calendar_features(grid_train)
    grid_val = add_calendar_features(grid_val)
    grid_sub = add_calendar_features(grid_sub)

    return grid_train, grid_val, grid_sub


def train_and_evaluate(
    data_dir: Path,
    output_dir: Path,
    use_gpu: bool = True,
    model_type: str = "catboost",
    iterations: int = 2000,
    learning_rate: float = 0.04,
    depth: int = 6,
    use_residual: bool = True,
    per_route: bool = True,
):
    output_dir.mkdir(parents=True, exist_ok=True)

    grid_train, grid_val, grid_sub = build_feature_matrix(data_dir)

    print(f"Train grid size: {len(grid_train):,} rows")
    print(f"Val grid size:   {len(grid_val):,} rows")
    print(f"Sub grid size:   {len(grid_sub):,} rows")

    # Step 1: Validation evaluation (profiles fitted ONLY on Train)
    print("\n--- STAGE 1: LOCAL VALIDATION (Train: Jan-Aug, Valid: Sep-Oct) ---")
    profiles_train = calculate_historical_profiles(grid_train)
    train_feat = attach_historical_profiles(grid_train, profiles_train)
    val_feat = attach_historical_profiles(grid_val, profiles_train)

    feature_cols = [
        "route",
        "hour",
        "dow_effective",
        "is_weekend",
        "is_holiday",
        "is_preholiday",
        "is_workday",
        "is_day_off",
        "is_summer",
        "is_morning_peak",
        "is_evening_peak",
        "is_night",
        "hour_sin",
        "hour_cos",
        "dow_sin",
        "dow_cos",
        "hist_mean_route_dow_hour",
        "hist_median_route_dow_hour",
        "hist_median_nonsummer_route_dow_hour",
        "hist_std_route_dow_hour",
        "hist_mean_route_dayoff_hour",
        "hist_median_route_dayoff_hour",
        "hist_mean_route_hour",
        "hist_mean_route",
    ]

    cat_features = ["route", "hour", "dow_effective"]

    # Base profile for residual learning: non-summer median (excludes summer vacation slump)
    base_col = "hist_median_nonsummer_route_dow_hour"
    base_train = train_feat[base_col].values
    base_val = val_feat[base_col].values

    X_train = train_feat[feature_cols]
    y_train = train_feat["boardings"].values
    X_val = val_feat[feature_cols]
    y_val = val_feat["boardings"].values

    if use_residual:
        print("Using Residual Learning (target = boardings - base_profile)...")
        y_train_fit = y_train - base_train
        y_val_fit = y_val - base_val
    else:
        y_train_fit = y_train
        y_val_fit = y_val

    model = None
    route_models = {}
    active_routes = [r for r in ALL_ROUTES if r != 5]
    route_feat_cols = [c for c in feature_cols if c != "route"]
    route_cat_features = [c for c in cat_features if c != "route"]

    if model_type == "catboost":
        try:
            from catboost import CatBoostRegressor
        except ImportError:
            raise ImportError("Please install catboost: pip install catboost")

        cb_params = {
            "loss_function": "MAE",
            "eval_metric": "MAE",
            "iterations": iterations,
            "learning_rate": learning_rate,
            "depth": depth,
            "random_seed": 42,
            "verbose": 0 if per_route else 200,
            "cat_features": route_cat_features if per_route else cat_features,
        }
        if use_gpu:
            cb_params["task_type"] = "GPU"
        else:
            cb_params["task_type"] = "CPU"
            cb_params["thread_count"] = -1

        if per_route:
            print("Training 9 specialized per-route CatBoost models...")
            val_preds = np.zeros(len(val_feat))
            for r in active_routes:
                mask_tr = (train_feat["route"] == r)
                mask_val = (val_feat["route"] == r)
                X_tr_r = train_feat.loc[mask_tr, route_feat_cols]
                y_tr_r = y_train_fit[mask_tr]
                X_val_r = val_feat.loc[mask_val, route_feat_cols]
                y_val_r = y_val_fit[mask_val]

                m_r = CatBoostRegressor(**cb_params)
                try:
                    m_r.fit(X_tr_r, y_tr_r, eval_set=(X_val_r, y_val_r), early_stopping_rounds=150, verbose=0)
                except Exception as e:
                    # fallback to CPU if GPU fails for small route
                    cb_params_cpu = cb_params.copy()
                    cb_params_cpu["task_type"] = "CPU"
                    cb_params_cpu["thread_count"] = -1
                    m_r = CatBoostRegressor(**cb_params_cpu)
                    m_r.fit(X_tr_r, y_tr_r, eval_set=(X_val_r, y_val_r), early_stopping_rounds=150, verbose=0)

                raw_preds_r = m_r.predict(X_val_r)
                if use_residual:
                    val_preds[mask_val] = base_val[mask_val] + raw_preds_r
                else:
                    val_preds[mask_val] = raw_preds_r
                route_models[r] = m_r
                r_wape = compute_wape_metrics(y_val[mask_val], val_preds[mask_val])
                print(f"  Route {r:2d} finished: best_iter={m_r.get_best_iteration():4d}, WAPE={r_wape['wape']:.4f}, WAPE-score={r_wape['wape_score']:.4f}")
        else:
            if use_gpu:
                try:
                    model = CatBoostRegressor(**cb_params)
                    model.fit(X_train, y_train_fit, eval_set=(X_val, y_val_fit), early_stopping_rounds=100, verbose=200)
                except Exception as e:
                    cb_params["task_type"] = "CPU"
                    cb_params["thread_count"] = -1
                    model = CatBoostRegressor(**cb_params)
                    model.fit(X_train, y_train_fit, eval_set=(X_val, y_val_fit), early_stopping_rounds=100, verbose=200)
            else:
                model = CatBoostRegressor(**cb_params)
                model.fit(X_train, y_train_fit, eval_set=(X_val, y_val_fit), early_stopping_rounds=100, verbose=200)

    elif model_type == "lightgbm":
        try:
            import lightgbm as lgb
        except ImportError:
            raise ImportError("Please install lightgbm: pip install lightgbm")

        lgb_params = {
            "objective": "mae",
            "metric": "mae",
            "learning_rate": learning_rate,
            "num_leaves": 2 ** depth - 1,
            "random_state": 42,
            "verbose": -1,
        }
        if use_gpu:
            lgb_params["device"] = "gpu"

        if per_route:
            print("Training 9 specialized per-route LightGBM models...")
            val_preds = np.zeros(len(val_feat))
            for r in active_routes:
                mask_tr = (train_feat["route"] == r)
                mask_val = (val_feat["route"] == r)
                X_tr_r = train_feat.loc[mask_tr, route_feat_cols]
                y_tr_r = y_train_fit[mask_tr]
                X_val_r = val_feat.loc[mask_val, route_feat_cols]
                y_val_r = y_val_fit[mask_val]

                dtrain = lgb.Dataset(X_tr_r, label=y_tr_r, categorical_feature=route_cat_features)
                dval = lgb.Dataset(X_val_r, label=y_val_r, reference=dtrain, categorical_feature=route_cat_features)

                m_r = lgb.train(
                    lgb_params,
                    dtrain,
                    num_boost_round=iterations,
                    valid_sets=[dtrain, dval],
                    callbacks=[lgb.early_stopping(stopping_rounds=100, verbose=False)],
                )
                raw_preds_r = m_r.predict(X_val_r)
                if use_residual:
                    val_preds[mask_val] = base_val[mask_val] + raw_preds_r
                else:
                    val_preds[mask_val] = raw_preds_r
                route_models[r] = m_r
        else:
            dtrain = lgb.Dataset(X_train, label=y_train_fit, categorical_feature=cat_features)
            dval = lgb.Dataset(X_val, label=y_val_fit, reference=dtrain, categorical_feature=cat_features)

            model = lgb.train(
                lgb_params,
                dtrain,
                num_boost_round=iterations,
                valid_sets=[dtrain, dval],
                callbacks=[lgb.early_stopping(stopping_rounds=100), lgb.log_evaluation(period=200)],
            )

    elif model_type == "baseline":
        print("Using historical seasonal profile baseline (pure numpy/pandas)...")

    elif model_type == "histgradient":
        from sklearn.ensemble import HistGradientBoostingRegressor
        print("Training Sklearn HistGradientBoostingRegressor with absolute_error (MAE) loss...")
        cat_indices = [feature_cols.index(c) for c in cat_features]
        model = HistGradientBoostingRegressor(
            loss="absolute_error",
            max_iter=min(iterations, 400),
            learning_rate=learning_rate,
            max_depth=depth,
            categorical_features=cat_indices,
            random_state=42,
        )
        model.fit(X_train, y_train_fit)

    # Evaluate validation predictions
    if model_type == "baseline":
        val_preds = base_val
    elif not per_route:
        raw_val_preds = model.predict(X_val)
        if use_residual:
            val_preds = base_val + raw_val_preds
        else:
            val_preds = raw_val_preds

    val_preds = np.clip(np.round(val_preds), 0, None)
    # Force route 5 to 0
    val_preds[X_val["route"] == 5] = 0

    val_metrics = compute_wape_metrics(y_val, val_preds)
    print("\n================ VALIDATION RESULTS (Sep-Oct 2025) ================")
    print(f"Overall MAE:        {val_metrics['mae']:.2f}")
    print(f"Overall WAPE:       {val_metrics['wape']:.4f} ({val_metrics['wape']*100:.2f}%)")
    print(f"Overall WAPE-score: {val_metrics['wape_score']:.4f}")
    print("Baseline was ~0.48. Higher is better!")
    print("===================================================================\n")

    # Per route breakdown
    val_analysis = val_feat[["route", "boardings"]].copy()
    val_analysis["pred"] = val_preds
    print("Per-Route WAPE Performance:")
    for r in sorted(val_analysis["route"].unique()):
        sub_r = val_analysis[val_analysis["route"] == r]
        m = compute_wape_metrics(sub_r["boardings"].values, sub_r["pred"].values)
        print(f"  Route {r:2d}: sum_y={int(sub_r['boardings'].sum()):8d}, WAPE={m['wape']:.4f}, WAPE-score={m['wape_score']:.4f}")

    # Step 2: Full re-training on all 10 months (Jan-Oct) for final submission
    print("\n--- STAGE 2: FULL RE-TRAINING (Jan-Oct 2025) FOR SUBMISSION ---")
    full_train = pd.concat([grid_train, grid_val], ignore_index=True)
    profiles_full = calculate_historical_profiles(full_train)

    full_train_feat = attach_historical_profiles(full_train, profiles_full)
    sub_feat = attach_historical_profiles(grid_sub, profiles_full)

    base_full = full_train_feat[base_col].values
    base_sub = sub_feat[base_col].values

    X_full = full_train_feat[feature_cols]
    y_full = full_train_feat["boardings"].values
    X_sub = sub_feat[feature_cols]

    if use_residual:
        y_full_fit = y_full - base_full
    else:
        y_full_fit = y_full

    final_model = None
    sub_preds = np.zeros(len(sub_feat), dtype=int)

    if model_type == "baseline":
        print("Using historical seasonal profile baseline for final submission...")
        sub_preds = base_sub
    elif per_route and model_type == "catboost":
        print("Fitting final per-route CatBoost models on full Jan-Oct history...")
        for r in active_routes:
            mask_full = (full_train_feat["route"] == r)
            mask_sub = (sub_feat["route"] == r)
            X_full_r = full_train_feat.loc[mask_full, route_feat_cols]
            y_full_r = y_full_fit[mask_full]
            X_sub_r = sub_feat.loc[mask_sub, route_feat_cols]

            best_iter = route_models[r].get_best_iteration() or iterations
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
            sub_preds[mask_sub] = np.clip(np.round(sub_pred_r), 0, None).astype(int)
    elif per_route and model_type == "lightgbm":
        print("Fitting final per-route LightGBM models on full Jan-Oct history...")
        for r in active_routes:
            mask_full = (full_train_feat["route"] == r)
            mask_sub = (sub_feat["route"] == r)
            X_full_r = full_train_feat.loc[mask_full, route_feat_cols]
            y_full_r = y_full_fit[mask_full]
            X_sub_r = sub_feat.loc[mask_sub, route_feat_cols]

            best_iter = route_models[r].best_iteration or iterations
            d_full_r = lgb.Dataset(X_full_r, label=y_full_r, categorical_feature=route_cat_features)
            final_m_r = lgb.train(lgb_params, d_full_r, num_boost_round=best_iter)
            raw_sub_r = final_m_r.predict(X_sub_r)
            sub_pred_r = (base_sub[mask_sub] + raw_sub_r) if use_residual else raw_sub_r
            sub_preds[mask_sub] = np.clip(np.round(sub_pred_r), 0, None).astype(int)
    elif model_type == "catboost":
        final_iterations = model.get_best_iteration() or iterations
        print(f"Training final CatBoost model on full data ({final_iterations} iterations)...")
        final_params = cb_params.copy()
        final_params["iterations"] = max(final_iterations, 300)
        final_model = CatBoostRegressor(**final_params)
        final_model.fit(X_full, y_full_fit, verbose=200)
        raw_sub = final_model.predict(X_sub)
        sub_preds = (base_sub + raw_sub) if use_residual else raw_sub
    elif model_type == "lightgbm":
        final_iterations = model.best_iteration or iterations
        print(f"Training final LightGBM model on full data ({final_iterations} iterations)...")
        d_full = lgb.Dataset(X_full, label=y_full_fit, categorical_feature=cat_features)
        final_model = lgb.train(lgb_params, d_full, num_boost_round=final_iterations)
        raw_sub = final_model.predict(X_sub)
        sub_preds = (base_sub + raw_sub) if use_residual else raw_sub
    elif model_type == "histgradient":
        from sklearn.ensemble import HistGradientBoostingRegressor
        print("Training final Sklearn HistGradientBoostingRegressor on full data...")
        cat_indices = [feature_cols.index(c) for c in cat_features]
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

    # Step 3: Predict November - December 2025
    print("\nGenerating predictions for November - December 2025...")
    sub_preds = np.clip(np.round(sub_preds), 0, None).astype(int)

    submission = grid_sub[["route", "date", "hour"]].copy()
    submission["prediction"] = sub_preds
    # Force route 5 strictly to 0
    submission.loc[submission["route"] == 5, "prediction"] = 0

    # Ensure format matches requirement strictly: route;date;hour;prediction
    sub_file = output_dir / "submission.csv"
    submission.to_csv(sub_file, sep=";", index=False)
    print(f"\nSUCCESS! Final submission file created at: {sub_file}")
    print(f"Rows count: {len(submission)} (expected exactly 14,640)")
    print(f"Sample preview:\n{submission.head(10)}")

    # Check against test_submission baseline
    test_sub_path = data_dir / "test_submission.csv"
    if test_sub_path.is_file():
        ref = pd.read_csv(test_sub_path, sep=";")
        print(f"\nVerification against baseline structure:")
        print(f"  Shape matches: {len(submission) == len(ref)}")
        print(f"  Columns match: {list(submission.columns) == list(ref.columns)}")
        print(f"  Total predicted passengers Nov-Dec: {submission['prediction'].sum():,}")
        print(f"  Baseline total predicted Nov-Dec:   {ref['prediction'].sum():,}")


def main():
    parser = argparse.ArgumentParser(description="Train tram ridership prediction model with GPU support.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("dataset"),
        help="Path to directory containing dataset files (labels/, test_submission.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/predictions"),
        help="Directory to save submission.csv and models",
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU execution (disable GPU)",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["catboost", "lightgbm", "histgradient", "baseline"],
        default="catboost",
        help="Model architecture: catboost (recommended for GPU), lightgbm, histgradient, or baseline (default: catboost)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=2000,
        help="Number of boosting iterations (default: 2000)",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.04,
        help="Learning rate (default: 0.04)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=6,
        help="Tree depth (default: 6)",
    )
    parser.add_argument(
        "--no-residual",
        action="store_true",
        help="Train directly on raw boardings rather than residual (delta) from base profile",
    )
    parser.add_argument(
        "--no-per-route",
        action="store_true",
        help="Train one single model for all routes instead of 9 dedicated per-route models",
    )

    args = parser.parse_args()
    train_and_evaluate(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        use_gpu=not args.cpu,
        model_type=args.model,
        iterations=args.iterations,
        learning_rate=args.learning_rate,
        depth=args.depth,
        use_residual=not args.no_residual,
        per_route=not args.no_per_route,
    )


if __name__ == "__main__":
    main()
