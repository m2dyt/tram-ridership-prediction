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
    df["day"] = dt.dt.day
    df["dayofyear"] = dt.dt.dayofyear
    df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)

    df["is_holiday"] = df["date"].isin(HOLIDAYS_2025).astype(int)
    df["is_preholiday"] = df["date"].isin(PRE_HOLIDAYS_2025).astype(int)
    df["is_workday"] = ((df["is_weekend"] == 0) & (df["is_holiday"] == 0)).astype(int)
    # Special: weekend day that operates as workday
    df["is_day_off"] = ((df["is_weekend"] == 1) | (df["is_holiday"] == 1)).astype(int)

    # Cyclical encodings
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["dow_sin"] = np.sin(2 * np.pi * df["dayofweek"] / 7)
    df["dow_cos"] = np.cos(2 * np.pi * df["dayofweek"] / 7)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # Peak hour indicators
    df["is_morning_peak"] = df["hour"].isin([7, 8, 9]).astype(int) * df["is_workday"]
    df["is_evening_peak"] = df["hour"].isin([17, 18, 19]).astype(int) * df["is_workday"]
    df["is_night"] = df["hour"].isin([1, 2, 3, 4]).astype(int)

    return df


def calculate_historical_profiles(train_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Calculate historical passenger profiles on train data only (no data leakage)."""
    # 1. Route x DayOfWeek x Hour profile
    prof_route_dow_hour = (
        train_df.groupby(["route", "dayofweek", "hour"])["boardings"]
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

    # 2. Route x IsDayOff x Hour profile (crucial for holidays)
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

    # 3. Route x Hour overall profile
    prof_route_hour = (
        train_df.groupby(["route", "hour"])["boardings"]
        .mean()
        .reset_index()
        .rename(columns={"boardings": "hist_mean_route_hour"})
    )

    # 4. Route overall volume
    prof_route = (
        train_df.groupby("route")["boardings"]
        .mean()
        .reset_index()
        .rename(columns={"boardings": "hist_mean_route"})
    )

    return {
        "prof_route_dow_hour": prof_route_dow_hour,
        "prof_route_dayoff_hour": prof_route_dayoff_hour,
        "prof_route_hour": prof_route_hour,
        "prof_route": prof_route,
    }


def attach_historical_profiles(df: pd.DataFrame, profiles: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Attach computed historical profiles to any dataset (train, val, or test)."""
    df = df.copy()

    df = df.merge(profiles["prof_route_dow_hour"], on=["route", "dayofweek", "hour"], how="left")
    df = df.merge(profiles["prof_route_dayoff_hour"], on=["route", "is_day_off", "hour"], how="left")
    df = df.merge(profiles["prof_route_hour"], on=["route", "hour"], how="left")
    df = df.merge(profiles["prof_route"], on=["route"], how="left")

    # For route 5 (or unknown combinations), fill NaNs with 0
    stat_cols = [
        "hist_mean_route_dow_hour",
        "hist_median_route_dow_hour",
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
    iterations: int = 1500,
    learning_rate: float = 0.05,
    depth: int = 7,
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
        "dayofweek",
        "month",
        "day",
        "dayofyear",
        "is_weekend",
        "is_holiday",
        "is_preholiday",
        "is_workday",
        "is_day_off",
        "is_morning_peak",
        "is_evening_peak",
        "is_night",
        "hour_sin",
        "hour_cos",
        "dow_sin",
        "dow_cos",
        "month_sin",
        "month_cos",
        "hist_mean_route_dow_hour",
        "hist_median_route_dow_hour",
        "hist_std_route_dow_hour",
        "hist_mean_route_dayoff_hour",
        "hist_median_route_dayoff_hour",
        "hist_mean_route_hour",
        "hist_mean_route",
    ]

    cat_features = ["route", "hour", "dayofweek"]

    X_train = train_feat[feature_cols]
    y_train = train_feat["boardings"].values
    X_val = val_feat[feature_cols]
    y_val = val_feat["boardings"].values

    model = None
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
            "verbose": 200,
            "cat_features": cat_features,
        }

        if use_gpu:
            print("Attempting to initialize CatBoost with NVIDIA GPU (task_type='GPU')...")
            try:
                # Test GPU availability
                cb_params["task_type"] = "GPU"
                model = CatBoostRegressor(**cb_params)
                model.fit(X_train, y_train, eval_set=(X_val, y_val), early_stopping_rounds=100, verbose=200)
                print("GPU training successful!")
            except Exception as e:
                print(f"GPU initialization failed ({e}). Falling back to multi-threaded CPU...")
                cb_params["task_type"] = "CPU"
                cb_params["thread_count"] = -1
                model = CatBoostRegressor(**cb_params)
                model.fit(X_train, y_train, eval_set=(X_val, y_val), early_stopping_rounds=100, verbose=200)
        else:
            cb_params["task_type"] = "CPU"
            cb_params["thread_count"] = -1
            model = CatBoostRegressor(**cb_params)
            model.fit(X_train, y_train, eval_set=(X_val, y_val), early_stopping_rounds=100, verbose=200)

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

        dtrain = lgb.Dataset(X_train, label=y_train, categorical_feature=cat_features)
        dval = lgb.Dataset(X_val, label=y_val, reference=dtrain, categorical_feature=cat_features)

        model = lgb.train(
            lgb_params,
            dtrain,
            num_boost_round=iterations,
            valid_sets=[dtrain, dval],
            callbacks=[lgb.early_stopping(stopping_rounds=100), lgb.log_evaluation(period=200)],
        )

    elif model_type == "baseline":
        print("Using historical seasonal profile baseline (pure numpy/pandas)...")
        # Predict directly from the historical profile hist_median_route_dow_hour
        val_preds = val_feat["hist_median_route_dow_hour"].values

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
        model.fit(X_train, y_train)

    # Evaluate validation predictions
    if model_type != "baseline":
        val_preds = model.predict(X_val)
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

    X_full = full_train_feat[feature_cols]
    y_full = full_train_feat["boardings"].values
    X_sub = sub_feat[feature_cols]

    final_model = None
    if model_type == "baseline":
        print("Using historical seasonal profile baseline for final submission...")
        sub_preds = sub_feat["hist_median_route_dow_hour"].values
    elif model_type == "catboost":
        final_iterations = model.get_best_iteration() or iterations
        print(f"Training final CatBoost model on full data ({final_iterations} iterations)...")
        final_params = cb_params.copy()
        final_params["iterations"] = max(final_iterations, 300)
        final_model = CatBoostRegressor(**final_params)
        final_model.fit(X_full, y_full, verbose=200)
        sub_preds = final_model.predict(X_sub)
    elif model_type == "lightgbm":
        final_iterations = model.best_iteration or iterations
        print(f"Training final LightGBM model on full data ({final_iterations} iterations)...")
        d_full = lgb.Dataset(X_full, label=y_full, categorical_feature=cat_features)
        final_model = lgb.train(lgb_params, d_full, num_boost_round=final_iterations)
        sub_preds = final_model.predict(X_sub)
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
        final_model.fit(X_full, y_full)
        sub_preds = final_model.predict(X_sub)

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
        default=1500,
        help="Number of boosting iterations (default: 1500)",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.06,
        help="Learning rate (default: 0.06)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=7,
        help="Tree depth (default: 7)",
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
    )


if __name__ == "__main__":
    main()
