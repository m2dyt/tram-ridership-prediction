"""Feature engineering and temporal grid generation for Tram Ridership Prediction."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

# Russian 2025 official non-working holidays and transferred days
HOLIDAYS_2025: set[str] = {
    # New Year holidays
    "2025-01-01",
    "2025-01-02",
    "2025-01-03",
    "2025-01-04",
    "2025-01-05",
    "2025-01-06",
    "2025-01-07",
    "2025-01-08",
    # Defender of Fatherland
    "2025-02-22",
    "2025-02-23",
    # International Women's Day
    "2025-03-08",
    "2025-03-09",
    # Spring and Labor
    "2025-05-01",
    "2025-05-02",
    "2025-05-03",
    "2025-05-04",
    # Victory Day
    "2025-05-08",
    "2025-05-09",
    "2025-05-10",
    "2025-05-11",
    # Russia Day
    "2025-06-12",
    "2025-06-13",
    "2025-06-14",
    "2025-06-15",
    # Unity Day
    "2025-11-02",
    "2025-11-03",
    "2025-11-04",
    # New Year Eve
    "2025-12-31",
}

# Pre-holidays (reduced working hours)
PRE_HOLIDAYS_2025: set[str] = {
    "2025-03-07",
    "2025-04-30",
    "2025-06-11",
    "2025-11-01",  # Saturday workday before Unity Day
}

ALL_ROUTES: list[int] = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]
ACTIVE_ROUTES: list[int] = [1, 7, 11, 12, 17, 25, 26, 28, 50]

FEATURE_COLS: list[str] = [
    "route",
    "hour",
    "dow_effective",
    "is_weekend",
    "is_holiday",
    "is_preholiday",
    "is_workday",
    "is_day_off",
    "is_summer",
    "is_cold_season",
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
    "hist_median_recent_route_dow_hour",
    "ratio_recent_to_nonsummer",
    "hist_std_route_dow_hour",
    "hist_mean_route_dayoff_hour",
    "hist_median_route_dayoff_hour",
    "hist_mean_route_hour",
    "hist_mean_route",
]

CATEGORICAL_FEATURES: list[str] = ["route", "hour", "dow_effective"]
ROUTE_FEATURE_COLS: list[str] = [c for c in FEATURE_COLS if c != "route"]
ROUTE_CAT_FEATURES: list[str] = [c for c in CATEGORICAL_FEATURES if c != "route"]


def generate_full_grid(
    start_date: str, end_date: str, routes: list[int] = ALL_ROUTES
) -> pd.DataFrame:
    """Generate a complete Cartesian grid of (date, hour, route) with all 24 hours."""
    dates = pd.date_range(start=start_date, end=end_date, freq="D").strftime("%Y-%m-%d")
    hours = list(range(24))

    grid = (
        pd.MultiIndex.from_product(
            [dates, hours, routes],
            names=["date", "hour", "route"],
        )
        .to_frame()
        .reset_index(drop=True)
    )

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
    df["is_cold_season"] = df["month"].isin([10, 11, 12, 1, 2, 3]).astype(int)

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
