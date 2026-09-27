"""Historical profile calculation and baseline predictors for Tram Ridership Prediction."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

BASE_PROFILE_COL = "hist_median_nonsummer_route_dow_hour"


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
        prof_route_dow_hour_nonsummer = prof_route_dow_hour[
            ["route", "dow_effective", "hour", "hist_median_route_dow_hour"]
        ].rename(columns={"hist_median_route_dow_hour": "hist_median_nonsummer_route_dow_hour"})

    # 3. Recent window profile (last 56 days / 8 weeks before the forecast cut-off)
    # For Sep-Oct val: this is July-August. For Nov-Dec final: this is Sep-Oct (autumn peak!).
    max_dt_str = str(train_df["date"].max())[:10]
    max_dt = datetime.strptime(max_dt_str, "%Y-%m-%d")
    recent_cutoff = (max_dt - timedelta(days=56)).strftime("%Y-%m-%d")
    recent_df = train_df[train_df["date"] >= recent_cutoff]

    prof_route_dow_hour_recent = (
        recent_df.groupby(["route", "dow_effective", "hour"])["boardings"]
        .median()
        .reset_index()
        .rename(columns={"boardings": "hist_median_recent_route_dow_hour"})
    )

    # 4. Weekend outage detection (e.g. Route 50 track repairs):
    recent_weekend = recent_df[recent_df["dow_effective"] >= 5]
    weekend_med = recent_weekend.groupby("route")["boardings"].median()
    closed_weekend_routes = [int(r) for r in weekend_med[weekend_med < 30].index.tolist() if r != 5]

    # 5. Night zero threshold: hours where 95% of historical observations are 0
    prof_night_q95 = (
        train_df.groupby(["route", "hour"])["boardings"]
        .quantile(0.95)
        .reset_index()
        .rename(columns={"boardings": "hist_q95_route_hour"})
    )

    # 6. Route x IsDayOff x Hour profile
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

    # 7. Route x Hour overall profile
    prof_route_hour = (
        train_df.groupby(["route", "hour"])["boardings"]
        .mean()
        .reset_index()
        .rename(columns={"boardings": "hist_mean_route_hour"})
    )

    # 8. Route overall volume
    prof_route = (
        train_df.groupby("route")["boardings"]
        .mean()
        .reset_index()
        .rename(columns={"boardings": "hist_mean_route"})
    )

    return {
        "prof_route_dow_hour": prof_route_dow_hour,
        "prof_route_dow_hour_nonsummer": prof_route_dow_hour_nonsummer,
        "prof_route_dow_hour_recent": prof_route_dow_hour_recent,
        "prof_night_q95": prof_night_q95,
        "prof_route_dayoff_hour": prof_route_dayoff_hour,
        "prof_route_hour": prof_route_hour,
        "prof_route": prof_route,
        "closed_weekend_routes": closed_weekend_routes,
    }


def attach_historical_profiles(df: pd.DataFrame, profiles: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Attach computed historical profiles to any dataset (train, val, or test)."""
    df = df.copy()

    df = df.merge(
        profiles["prof_route_dow_hour"], on=["route", "dow_effective", "hour"], how="left"
    )
    df = df.merge(
        profiles["prof_route_dow_hour_nonsummer"], on=["route", "dow_effective", "hour"], how="left"
    )
    df = df.merge(
        profiles["prof_route_dow_hour_recent"], on=["route", "dow_effective", "hour"], how="left"
    )
    df = df.merge(profiles["prof_night_q95"], on=["route", "hour"], how="left")
    df = df.merge(
        profiles["prof_route_dayoff_hour"], on=["route", "is_day_off", "hour"], how="left"
    )
    df = df.merge(profiles["prof_route_hour"], on=["route", "hour"], how="left")
    df = df.merge(profiles["prof_route"], on=["route"], how="left")

    # If recent is missing, fallback to nonsummer
    if "hist_median_recent_route_dow_hour" in df.columns:
        df["hist_median_recent_route_dow_hour"] = df["hist_median_recent_route_dow_hour"].fillna(
            df["hist_median_nonsummer_route_dow_hour"]
        )

    # Blended base profile: 70% recent + 30% long-term non-summer
    # (Captures current capacity and fleet while maintaining long-term stability)
    df["hist_median_blend_route_dow_hour"] = (
        0.7 * df["hist_median_recent_route_dow_hour"]
        + 0.3 * df["hist_median_nonsummer_route_dow_hour"]
    )

    # Physical transport network adjustments:
    # 1. Route 50 weekend closure (track reconstruction Baumanskaya-Aviamotornaya)
    mask_r50_wk = (df["route"] == 50) & (df["dow_effective"] >= 5)
    df.loc[mask_r50_wk, "hist_median_nonsummer_route_dow_hour"] = 0.0

    # 2. Route 7 weekend shortening (truncated to Kalanchevskaya due to same track works)
    mask_r7_wk = (df["route"] == 7) & (df["dow_effective"] >= 5)
    df.loc[mask_r7_wk, "hist_median_nonsummer_route_dow_hour"] *= 0.60

    # 3. Autumn-winter weekend ridership growth on trunk routes
    mask_r17_wk = (df["route"] == 17) & (df["dow_effective"] >= 5)
    df.loc[mask_r17_wk, "hist_median_nonsummer_route_dow_hour"] *= 1.15

    mask_r25_wk = (df["route"] == 25) & (df["dow_effective"] >= 5)
    df.loc[mask_r25_wk, "hist_median_nonsummer_route_dow_hour"] *= 1.18

    # 4. Cold season workday general uplift (+4% in October, November, December)
    mask_cold_work = (df["is_cold_season"] == 1) & (df["dow_effective"] < 5)
    df.loc[mask_cold_work, "hist_median_nonsummer_route_dow_hour"] *= 1.04

    # For nocturnal hours where 95% of observations are 0:
    mask_night_zero = df["hist_q95_route_hour"] == 0
    df.loc[mask_night_zero, "hist_median_nonsummer_route_dow_hour"] = 0.0

    df["ratio_recent_to_nonsummer"] = (df["hist_median_recent_route_dow_hour"] + 1.0) / (
        df["hist_median_nonsummer_route_dow_hour"] + 1.0
    )

    stat_cols = [
        "hist_mean_route_dow_hour",
        "hist_median_route_dow_hour",
        "hist_median_nonsummer_route_dow_hour",
        "hist_median_recent_route_dow_hour",
        "ratio_recent_to_nonsummer",
        "hist_q95_route_hour",
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


def predict_seasonal_baseline(df_feat: pd.DataFrame) -> np.ndarray:
    """Generate baseline prediction using seasonal profile with postprocessing."""
    preds = df_feat[BASE_PROFILE_COL].values.copy()
    preds = np.clip(np.round(preds), 0, None)
    # Force route 5 strictly to 0
    if "route" in df_feat.columns:
        preds[df_feat["route"].values == 5] = 0
    return preds
