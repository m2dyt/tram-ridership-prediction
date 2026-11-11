"""ArtifactPredictor: ML infrastructure adapter for TramModelBundle serving in backend."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ml.training.tram import adaptive
from ml.training.tram.bundle import (
    TramModelBundle,
    get_active_version,
    load_model_bundle,
)
from tram.application.models import BUNDLE_METHOD
from tram.application.ports import Predictor
from tram.domain.series import Observation, Prediction, SpatialKey, SpatialLevel
from tram.domain.time import (
    MOSCOW,
    Horizon,
    Interval,
    Resolution,
    aware,
    intervals,
)

logger = logging.getLogger(__name__)


class ArtifactPredictor:
    """Infrastructure adapter connecting versioned TramModelBundle to backend Predictor port."""

    def __init__(
        self,
        bundle: TramModelBundle,
        fallback: Predictor | None = None,
    ):
        self.bundle = bundle
        self.fallback = fallback
        # One method name for every bundle; the version is pinned separately in the run.
        self.method = BUNDLE_METHOD
        self.version = bundle.version
        config = bundle.config or {}
        self.adaptive = config.get("recipe") == adaptive.RECIPE
        # The worker passes every series of a route in one call (and the route history for
        # stop forecasts), because stop values are shares of the route forecast.
        self.joint_route_series = self.adaptive
        if config.get("use_weather"):
            # At serving time only a weather forecast would be known; the service has no such
            # source, and filling in average weather silently would bias the model.
            raise ValueError(
                f"Model bundle {bundle.version} uses weather features, but the service has no "
                "weather forecast source"
            )

    @classmethod
    def from_version(cls, models_root: Path, version: str) -> ArtifactPredictor:
        """Strictly load one bundle version for the worker.

        No fallback predictor: failures surface as exceptions at startup and as
        explicit run failures later, never as a seasonal forecast in disguise.
        """
        return cls(bundle=load_model_bundle(version, models_root=models_root), fallback=None)

    @classmethod
    def from_active_version(
        cls,
        models_root: Path = Path("models/tram"),
        fallback: Predictor | None = None,
        specific_version: str | None = None,
    ) -> ArtifactPredictor | None:
        """Factory method to load active or specified version bundle."""
        target_version = specific_version or get_active_version(models_root=models_root)
        if not target_version:
            logger.info("No active model bundle version configured in %s", models_root)
            return None

        try:
            bundle = load_model_bundle(target_version, models_root=models_root)
            logger.info("Loaded ArtifactPredictor with model bundle '%s'", target_version)
            return cls(bundle=bundle, fallback=fallback)
        except Exception as e:
            logger.warning(
                "Failed to load model bundle '%s': %s. Falling back.",
                target_version,
                e,
            )
            return None

    def predict(
        self,
        history: Iterable[Observation],
        series: tuple[SpatialKey, ...],
        window: Interval,
        horizon: Horizon,
        resolution: Resolution,
        as_of: datetime,
    ) -> tuple[Prediction, ...]:
        if self.adaptive:
            return self._predict_adaptive(history, series, window, resolution, as_of)
        # ArtifactPredictor specializes in hourly route forecasts
        if resolution != Resolution.HOUR:
            if self.fallback:
                return self.fallback.predict(history, series, window, horizon, resolution, as_of)
            raise ValueError(f"ArtifactPredictor supports only Resolution.HOUR, got {resolution}")

        # Check if route numbers are valid integers
        routes: list[tuple[SpatialKey, int]] = []
        for s in series:
            try:
                r_int = int(s.route_id)
                routes.append((s, r_int))
            except ValueError:
                if self.fallback:
                    return self.fallback.predict(
                        history, series, window, horizon, resolution, as_of
                    )
                raise

        window_intervals = list(intervals(window, resolution))
        if not window_intervals:
            return ()

        # Build query grid for bundle prediction
        records = []
        query_map = []
        for interval in window_intervals:
            local_dt = interval.start.astimezone(MOSCOW)
            date_str = local_dt.strftime("%Y-%m-%d")
            hour_int = local_dt.hour
            for spatial, r_int in routes:
                records.append({"date": date_str, "hour": hour_int, "route": r_int})
                query_map.append((spatial, interval))

        df_query = pd.DataFrame(records)

        try:
            raw_preds = self.bundle.predict(df_query)
        except Exception as e:
            logger.warning("Bundle prediction failed: %s. Using fallback.", e)
            if self.fallback:
                return self.fallback.predict(history, series, window, horizon, resolution, as_of)
            raise

        predictions = []
        ref_start = aware(as_of)
        for (spatial, interval), val in zip(query_map, raw_preds, strict=True):
            predictions.append(
                Prediction(
                    spatial=spatial,
                    interval=interval,
                    value=float(val),
                    missing_reason=None,
                    reference_start=ref_start,
                )
            )

        return tuple(predictions)

    def _predict_adaptive(self, history, series, window, resolution, as_of):
        """Route forecast from fresh profiles; stop forecasts are shares of it."""
        if resolution != Resolution.HOUR:
            raise ValueError(f"Model bundle forecasts hourly values, got {resolution}")
        hours = list(intervals(window, resolution))
        if not hours or not series:
            return ()
        route_ids = {key.route_id for key in series}
        if len(route_ids) != 1:
            raise ValueError("Series of one call must belong to one route")
        route_id = next(iter(route_ids))
        observations = tuple(history)
        route_rows = _rows(o for o in observations if o.spatial.level == SpatialLevel.ROUTE)
        stop_obs = [o for o in observations if o.spatial.level == SpatialLevel.STOP]
        if route_rows.empty and stop_obs:
            # No route-level profile in the dataset: the stops of a route add up to it.
            route_rows = (
                _rows(stop_obs).groupby(["date", "hour"], as_index=False)["boardings"].sum()
            )
        route_rows = route_rows.assign(route=_route_number(route_id))
        target = pd.DataFrame(
            {
                "route": _route_number(route_id),
                "date": [h.start.astimezone(MOSCOW).strftime("%Y-%m-%d") for h in hours],
                "hour": [h.start.astimezone(MOSCOW).hour for h in hours],
            }
        )
        values, lower, upper = adaptive.forecast(self.bundle.models, route_rows, target)
        shares = _stop_shares(series, stop_obs, self.bundle.models.get("recent_days", 28))
        band_info = self.bundle.models.get("intervals") or {}
        reference = aware(as_of)
        predictions = []
        for key in series:
            share = shares.get(key.canonical, 1.0)
            for index, interval in enumerate(hours):
                value = values[index]
                if not np.isfinite(value):
                    predictions.append(
                        Prediction(key, interval, None, "insufficient_history", reference)
                    )
                    continue
                band = None
                if lower is not None:
                    band = {
                        "lower": float(lower[index] * share),
                        "upper": float(upper[index] * share),
                        "nominal_coverage": float(band_info["nominal_coverage"]),
                        "method": band_info["method"],
                    }
                predictions.append(
                    Prediction(key, interval, float(value * share), None, reference, band)
                )
        return tuple(predictions)


def _route_number(route_id: str):
    try:
        return int(route_id)
    except ValueError:
        return route_id


def _rows(observations) -> pd.DataFrame:
    """Observations as route/date/hour rows in Moscow time; a missing value is zero boardings."""
    records = []
    for observation in observations:
        start = observation.interval.start.astimezone(MOSCOW)
        records.append(
            {
                "date": start.strftime("%Y-%m-%d"),
                "hour": start.hour,
                "boardings": float(observation.value or 0.0),
            }
        )
    return pd.DataFrame(records, columns=["date", "hour", "boardings"])


def _stop_shares(series, stop_obs, recent_days):
    """Share of each stop in the route total over the recent window of the stop history."""
    stops = [key for key in series if key.level == SpatialLevel.STOP]
    if not stops:
        return {}
    if not stop_obs:
        return {key.canonical: 1.0 / len(stops) for key in stops}
    last = max(o.interval.start for o in stop_obs)
    totals = {key.canonical: 0.0 for key in stops}
    for observation in stop_obs:
        age = (last - observation.interval.start).total_seconds() / 86400
        if observation.spatial.canonical in totals and age < recent_days:
            totals[observation.spatial.canonical] += float(observation.value or 0.0)
    whole = sum(totals.values())
    if whole <= 0:
        return {key: 1.0 / len(stops) for key in totals}
    return {key: total / whole for key, total in totals.items()}
