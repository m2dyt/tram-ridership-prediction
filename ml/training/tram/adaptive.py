"""Adaptive service model: profiles from fresh history plus a residual model.

The same functions are used for training and for serving, so the model always sees
features built the way they will be built in production:

1. Base. For every route, effective day of week and hour the base is the median of the
   last ``recent_days`` days of history of the same season type (summer or not). It is
   recomputed from the history available at the forecast moment, so track works, a new
   timetable or the autumn rise reach the forecast without hand-made coefficients.
2. Residual model. HistGradientBoosting with MAE loss learns ``actual - base`` from
   calendar features and the profile features. Training rows get their profile features
   from history strictly before their week (time-aware features), like at serving time.
3. Choice. The last ``holdout_weeks`` weeks are held out. The residual model is used only
   if it beats the base alone there; otherwise the bundle serves the base.
4. Prediction interval. Quantiles of holdout errors by hour band (night, day, peak) give an
   80 % interval: forecast + q10 ... forecast + q90 (split conformal prediction).
5. Final fit. After the holdout check the model is refitted on all history.

Routes with no boardings in the recent window (route 5 under reconstruction) get zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ml.training.tram.features import add_calendar_features

RECIPE = "adaptive_v2"
RECENT_DAYS = 28
MIN_HISTORY_DAYS = 28
HOLDOUT_WEEKS = 8
INTERVAL_LEVEL = 0.8
KEY = ["route", "dow_effective", "hour"]
PEAK_HOURS = {7, 8, 9, 17, 18, 19}
CALENDAR_FEATURES = [
    "route",
    "hour",
    "dow_effective",
    "is_weekend",
    "is_holiday",
    "is_preholiday",
    "is_workday",
    "is_day_off",
    "is_cold_season",
    "is_morning_peak",
    "is_evening_peak",
    "is_night",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]
PROFILE_FEATURES = ["long", "recent", "recent_dayoff", "std", "ratio"]
FEATURES = CALENDAR_FEATURES + PROFILE_FEATURES
CATEGORICAL = ["route", "hour", "dow_effective"]
DEFAULT_PARAMS = {
    "max_iter": 80,
    "learning_rate": 0.05,
    "max_depth": 4,
    "min_samples_leaf": 200,
    "l2_regularization": 1.0,
}


def hour_band(hours) -> np.ndarray:
    hours = np.asarray(hours)
    return np.select(
        [np.isin(hours, list(PEAK_HOURS)), (hours >= 6) & (hours <= 21)], ["peak", "day"], "night"
    )


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Add calendar features, a date column ``d`` and the summer flag to route/date/hour rows."""
    df = frame.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = add_calendar_features(df)
    df["d"] = pd.to_datetime(df["date"])
    df["summer"] = df["d"].dt.month.isin([6, 7, 8])
    return df


def complete_grid(observed: pd.DataFrame, until=None) -> pd.DataFrame:
    """Hourly grid from each route's first day to ``until`` (default: the last observed day
    of any route); hours without data are zero.

    Validations are counted per hour, so an hour without a record means no boardings. A route
    whose records stop (closed for works) therefore gets zeros up to the end, not a gap.
    """
    if observed.empty:
        return observed.assign(boardings=pd.Series(dtype=float))
    last = pd.Timestamp(until) if until is not None else pd.to_datetime(observed["date"]).max()
    parts = []
    for route, rows in observed.groupby("route"):
        days = pd.date_range(pd.to_datetime(rows["date"]).min(), last, freq="D")
        grid = pd.MultiIndex.from_product(
            [days.strftime("%Y-%m-%d"), range(24)], names=["date", "hour"]
        )
        series = rows.groupby(["date", "hour"])["boardings"].sum().reindex(grid, fill_value=0.0)
        parts.append(series.reset_index().assign(route=route))
    return pd.concat(parts, ignore_index=True)[["route", "date", "hour", "boardings"]]


def profile_features(history: pd.DataFrame, target: pd.DataFrame, recent_days: int) -> pd.DataFrame:
    """Profile features of ``target`` rows from ``history`` (already cut at the forecast moment)."""
    out = target[["route", "dow_effective", "hour", "is_day_off", "summer"]].copy()
    if history.empty:
        for column in [*PROFILE_FEATURES, "base", "recent_total"]:
            out[column] = np.nan
        return out
    not_summer = history[~history["summer"]]
    source = not_summer if len(not_summer) else history
    out = out.join(source.groupby(KEY)["boardings"].median().rename("long"), on=KEY)
    pieces = []
    for is_summer, rows in out.groupby("summer", sort=False):
        same = history[history["summer"] == is_summer]
        if same.empty:
            same = history
        recent = same[same["d"] > same["d"].max() - pd.Timedelta(days=recent_days)]
        piece = rows[["route", "dow_effective", "hour", "is_day_off"]]
        piece = piece.join(recent.groupby(KEY)["boardings"].median().rename("recent"), on=KEY)
        piece = piece.join(
            recent.groupby(["route", "is_day_off", "hour"])["boardings"]
            .median()
            .rename("recent_dayoff"),
            on=["route", "is_day_off", "hour"],
        )
        piece = piece.join(
            recent.groupby("route")["boardings"].sum().rename("recent_total"), on="route"
        )
        pieces.append(piece[["recent", "recent_dayoff", "recent_total"]])
    out = out.join(pd.concat(pieces))
    out["recent"] = out["recent"].fillna(out["recent_dayoff"]).fillna(out["long"])
    out["long"] = out["long"].fillna(out["recent"])
    out = out.join(history.groupby(KEY)["boardings"].std().rename("std"), on=KEY)
    out["ratio"] = (out["recent"] + 1.0) / (out["long"] + 1.0)
    out["base"] = out["recent"]
    return out


def time_aware_frame(
    full: pd.DataFrame, start, end, recent_days: int = RECENT_DAYS, step_days: int = 7
) -> pd.DataFrame:
    """Rows of [start, end) in weekly blocks; each block sees only history before it."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    parts = []
    block_start = start
    while block_start < end:
        block_end = min(block_start + pd.Timedelta(days=step_days), end)
        block = full[(full["d"] >= block_start) & (full["d"] < block_end)]
        if len(block):
            features = profile_features(full[full["d"] < block_start], block, recent_days)
            parts.append(
                pd.concat(
                    [
                        block[[*CALENDAR_FEATURES, "boardings", "d", "date"]],
                        features[[*PROFILE_FEATURES, "base", "recent_total"]],
                    ],
                    axis=1,
                )
            )
        block_start = block_end
    return pd.concat(parts) if parts else pd.DataFrame()


def fit_residual(train: pd.DataFrame, params: dict[str, Any] | None = None, seed: int = 42):
    from sklearn.ensemble import HistGradientBoostingRegressor

    rows = train.dropna(subset=["base"])
    model = HistGradientBoostingRegressor(
        loss="absolute_error",
        categorical_features=[FEATURES.index(name) for name in CATEGORICAL],
        random_state=seed,
        **(params or DEFAULT_PARAMS),
    )
    model.fit(rows[FEATURES].fillna(-1.0), rows["boardings"] - rows["base"])
    return model


def point_forecast(model, frame: pd.DataFrame) -> np.ndarray:
    """Base plus the residual model (if any), clipped at zero; inactive routes give zero."""
    base = frame["base"].fillna(0.0).to_numpy(dtype=float)
    values = base + (model.predict(frame[FEATURES].fillna(-1.0)) if model is not None else 0.0)
    values = np.clip(values, 0.0, None)
    values[frame["recent_total"].fillna(0.0).to_numpy() <= 0] = 0.0
    return values


def interval_bounds(values: np.ndarray, hours, quantiles: dict[str, dict[str, float]]):
    bands = hour_band(hours)
    low = np.array([quantiles[band]["low"] for band in bands], dtype=float)
    high = np.array([quantiles[band]["high"] for band in bands], dtype=float)
    # The range always contains the forecast itself: lower <= value <= upper.
    lower = np.clip(np.minimum(values + low, values), 0.0, None)
    upper = np.maximum(values + high, values)
    zero = values <= 0
    lower[zero], upper[zero] = 0.0, 0.0
    return lower, upper


def residual_quantiles(errors: np.ndarray, hours, level: float = INTERVAL_LEVEL):
    alpha = (1.0 - level) / 2.0
    bands = hour_band(hours)
    result = {}
    for band in ("night", "day", "peak"):
        chosen = errors[bands == band]
        if len(chosen) == 0:
            chosen = errors
        result[band] = {
            "low": float(np.quantile(chosen, alpha)),
            "high": float(np.quantile(chosen, 1.0 - alpha)),
        }
    return result


def wape(actual, forecast) -> float:
    actual, forecast = np.asarray(actual, dtype=float), np.asarray(forecast, dtype=float)
    total = actual.sum()
    return float(np.abs(actual - forecast).sum() / total) if total > 0 else 0.0


def _scores(frame: pd.DataFrame, values: np.ndarray) -> dict[str, Any]:
    actual = frame["boardings"].to_numpy(dtype=float)
    error = float(wape(actual, values))
    overall = {
        "wape": error,
        "wape_score": max(0.0, 1.0 - error),
        "mae": float(np.mean(np.abs(actual - values))),
        "sum_y": float(actual.sum()),
        "sum_abs_err": float(np.abs(actual - values).sum()),
        "count": int(len(actual)),
    }
    per_route = {}
    for route, index in frame.groupby("route").indices.items():
        route_actual, route_values = actual[index], values[index]
        route_error = wape(route_actual, route_values)
        per_route[str(route)] = {
            "wape": route_error,
            "wape_score": max(0.0, 1.0 - route_error) if route_actual.sum() > 0 else 1.0,
            "mae": float(np.mean(np.abs(route_actual - route_values))),
            "sum_y": float(route_actual.sum()),
            "sum_abs_err": float(np.abs(route_actual - route_values).sum()),
            "count": int(len(index)),
        }
    return {"overall": overall, "per_route": per_route}


@dataclass
class ServiceTraining:
    check_model: Any
    final_model: Any
    use_model: bool
    metrics: dict[str, Any]
    intervals: dict[str, Any]
    history_start: pd.Timestamp
    holdout_start: pd.Timestamp
    history_end: pd.Timestamp
    routes: list[int] = field(default_factory=list)


def train_service_model(
    observed: pd.DataFrame,
    holdout_weeks: int = HOLDOUT_WEEKS,
    recent_days: int = RECENT_DAYS,
    params: dict[str, Any] | None = None,
) -> ServiceTraining:
    """Holdout check, model choice, interval calibration and the final refit."""
    full = prepare(complete_grid(observed))
    first, last = full["d"].min(), full["d"].max()
    history_end = last + pd.Timedelta(days=1)
    holdout_start = history_end - pd.Timedelta(days=int(7 * holdout_weeks))
    train_start = first + pd.Timedelta(days=int(MIN_HISTORY_DAYS))
    if holdout_start <= train_start + pd.Timedelta(days=28):
        raise ValueError("Not enough history for a holdout check: need at least 3 months")

    train = time_aware_frame(full, train_start, holdout_start, recent_days)
    holdout = time_aware_frame(full, holdout_start, history_end, recent_days)
    check_model = fit_residual(train, params)
    base_values = point_forecast(None, holdout)
    model_values = point_forecast(check_model, holdout)
    base_scores, model_scores = _scores(holdout, base_values), _scores(holdout, model_values)
    use_model = model_scores["overall"]["wape"] < base_scores["overall"]["wape"]
    chosen = model_values if use_model else base_values

    # Interval: calibrate on the first half of the holdout, report coverage on the second,
    # then store quantiles from the whole holdout for serving.
    errors = holdout["boardings"].to_numpy(dtype=float) - chosen
    hours = holdout["hour"].to_numpy()
    middle = holdout_start + pd.Timedelta(days=int(7 * (holdout_weeks // 2)))
    first_half = (holdout["d"] < middle).to_numpy()
    active = chosen > 0
    check_q = residual_quantiles(errors[first_half & active], hours[first_half & active])
    low, high = interval_bounds(chosen[~first_half], hours[~first_half], check_q)
    actual_second = holdout["boardings"].to_numpy(dtype=float)[~first_half]
    measured = float(np.mean((actual_second >= low) & (actual_second <= high)))
    quantiles = residual_quantiles(errors[active], hours[active])
    intervals = {
        "method": "split_conformal_hour_band_v1",
        "nominal_coverage": INTERVAL_LEVEL,
        "quantiles": quantiles,
        "check_coverage": measured,
        "check_period": [middle.strftime("%Y-%m-%d"), history_end.strftime("%Y-%m-%d")],
    }
    final_model = None
    if use_model:
        final_model = fit_residual(
            time_aware_frame(full, train_start, history_end, recent_days), params
        )
    chosen_scores = model_scores if use_model else base_scores
    metrics = {
        **chosen_scores,
        "selected": "model" if use_model else "base",
        "holdout": {
            "start": holdout_start.strftime("%Y-%m-%d"),
            "end": history_end.strftime("%Y-%m-%d"),
            "weeks": holdout_weeks,
            "base_wape": base_scores["overall"]["wape"],
            "model_wape": model_scores["overall"]["wape"],
        },
        "intervals": intervals,
    }
    return ServiceTraining(
        check_model=check_model,
        final_model=final_model,
        use_model=use_model,
        metrics=metrics,
        intervals=intervals,
        history_start=first,
        holdout_start=holdout_start,
        history_end=history_end,
        routes=sorted(int(route) for route in full["route"].unique()),
    )


def forecast(
    estimator: dict[str, Any],
    history: pd.DataFrame,
    target: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    """Serve one route block: ``history`` rows (route, date, hour, boardings) up to as_of,
    ``target`` rows (route, date, hour). Returns values and the interval bounds."""
    recent_days = int(estimator.get("recent_days", RECENT_DAYS))
    day_before = pd.to_datetime(target["date"]).min() - pd.Timedelta(days=1)
    hist = prepare(complete_grid(history, until=day_before)) if len(history) else pd.DataFrame()
    tgt = prepare(target.assign(boardings=0.0))
    if hist.empty:
        values = np.full(len(tgt), np.nan)
        return values, None, None
    features = profile_features(hist, tgt, recent_days)
    frame = pd.concat(
        [tgt[CALENDAR_FEATURES], features[[*PROFILE_FEATURES, "base", "recent_total"]]], axis=1
    )
    values = point_forecast(estimator.get("model") if estimator.get("use_model") else None, frame)
    quantiles = (estimator.get("intervals") or {}).get("quantiles")
    if not quantiles:
        return values, None, None
    lower, upper = interval_bounds(values, tgt["hour"].to_numpy(), quantiles)
    return values, lower, upper
