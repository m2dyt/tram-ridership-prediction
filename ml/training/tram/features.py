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

WEATHER_FEATURE_COLS: list[str] = [
    "temperature_2m",
    "precipitation",
    "snowfall",
    "wind_speed_10m",
    "is_freezing",
    "is_precipitation",
    "is_snow",
    "is_heavy_snow",
]

BASE_FEATURE_COLS: list[str] = [
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

ROUTE_STATIC_FEATURE_COLS: list[str] = [
    "route_is_active",
    "route_num_stops",
    "route_length_km",
    "route_metro_stops",
    "route_metro_ratio",
    "route_center_dist_km",
    "route_mean_delay_min",
    "route_late_ratio",
    "route_punctuality_ratio",
    "route_delay_std",
    "route_fleet_proxy",
    "route_segregated_ratio",
    "route_shared_stops",
]

FEATURE_COLS: list[str] = BASE_FEATURE_COLS + WEATHER_FEATURE_COLS + ROUTE_STATIC_FEATURE_COLS

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


def attach_weather_features(
    df: pd.DataFrame,
    weather_df: pd.DataFrame | None = None,
    weather_path: Path | None = None,
) -> pd.DataFrame:
    """Attach normalized Moscow hourly weather to dataset."""
    df = df.copy()

    if weather_df is None:
        if weather_path is None:
            # Look in standard locations
            candidate_paths = [
                Path("data/weather_hourly_2025.csv"),
                Path("../data/weather_hourly_2025.csv"),
                Path("../../data/weather_hourly_2025.csv"),
            ]
            for p in candidate_paths:
                if p.is_file():
                    weather_path = p
                    break

        if weather_path and weather_path.is_file():
            weather_df = pd.read_csv(weather_path)

    if weather_df is not None:
        # Select required columns
        join_cols = ["date", "hour"] + [c for c in WEATHER_FEATURE_COLS if c in weather_df.columns]
        w_sub = weather_df[join_cols].drop_duplicates(subset=["date", "hour"])
        df = df.merge(w_sub, on=["date", "hour"], how="left")

    # Fill any missing weather values with neutral defaults
    default_values = {
        "temperature_2m": 5.0,
        "precipitation": 0.0,
        "snowfall": 0.0,
        "wind_speed_10m": 10.0,
        "is_freezing": 0,
        "is_precipitation": 0,
        "is_snow": 0,
        "is_heavy_snow": 0,
    }
    for col in WEATHER_FEATURE_COLS:
        if col not in df.columns:
            df[col] = default_values[col]
        else:
            df[col] = df[col].fillna(default_values[col])

    return df


def attach_route_features(
    df: pd.DataFrame,
    route_features_df: pd.DataFrame | None = None,
    route_features_path: Path | None = None,
) -> pd.DataFrame:
    """Attach static spatial and operational telemetry features to route grid."""
    df = df.copy()

    if route_features_df is None:
        if route_features_path is None:
            candidate_paths = [
                Path("data/tram_route_features.csv"),
                Path("../data/tram_route_features.csv"),
                Path("../../data/tram_route_features.csv"),
            ]
            for p in candidate_paths:
                if p.is_file():
                    route_features_path = p
                    break

        if route_features_path and route_features_path.is_file():
            route_features_df = pd.read_csv(route_features_path)

    if route_features_df is not None:
        join_cols = ["route"] + [
            c for c in ROUTE_STATIC_FEATURE_COLS if c in route_features_df.columns
        ]
        rf_sub = route_features_df[join_cols].drop_duplicates(subset=["route"])
        df = df.merge(rf_sub, on="route", how="left")

    # Fill defaults for any missing static columns
    for col in ROUTE_STATIC_FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].fillna(0.0)

    return df


def build_feature_matrix(
    data_dir: Path,
    use_weather: bool = True,
    weather_path: Path | None = None,
    use_route_features: bool = True,
    route_features_path: Path | None = None,
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

    # Add weather features if enabled
    if use_weather:
        print("Attaching hourly weather features (temperature, precipitation, snow, wind)...")
        w_path = weather_path or Path("data/weather_hourly_2025.csv")
        grid_train = attach_weather_features(grid_train, weather_path=w_path)
        grid_val = attach_weather_features(grid_val, weather_path=w_path)
        grid_sub = attach_weather_features(grid_sub, weather_path=w_path)

    # Add route spatial & operational telemetry features if enabled
    if use_route_features:
        print("Attaching route spatial & operational telemetry features...")
        rf_path = route_features_path or Path("data/tram_route_features.csv")
        grid_train = attach_route_features(grid_train, route_features_path=rf_path)
        grid_val = attach_route_features(grid_val, route_features_path=rf_path)
        grid_sub = attach_route_features(grid_sub, route_features_path=rf_path)

    return grid_train, grid_val, grid_sub
