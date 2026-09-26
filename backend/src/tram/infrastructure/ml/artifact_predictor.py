"""ArtifactPredictor: ML infrastructure adapter for TramModelBundle serving in backend."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
import pandas as pd

from tram.application.ports import Predictor
from tram.domain.series import Observation, Prediction, SpatialKey
from tram.domain.time import (
    MOSCOW,
    Horizon,
    Interval,
    Resolution,
    aware,
    intervals,
)
from ml.training.tram.bundle import (
    TramModelBundle,
    load_model_bundle,
    get_active_version,
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
        self.method = f"tram_bundle_{bundle.version}"

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
                    return self.fallback.predict(history, series, window, horizon, resolution, as_of)
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
