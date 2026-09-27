"""Unit and integration tests for ArtifactPredictor and backend worker wiring."""

import unittest
from datetime import UTC, datetime
from pathlib import Path

from tram.domain.series import SpatialKey, SpatialLevel
from tram.domain.time import Horizon, Interval, Resolution, aware
from tram.infrastructure.ml.artifact_predictor import ArtifactPredictor

from ml.training.tram.bundle import get_active_version

try:
    from tram_ml.baseline import SeasonalNaive
except ImportError:
    SeasonalNaive = None


class TestArtifactPredictor(unittest.TestCase):
    def setUp(self):
        self.models_root = Path("models/tram")
        self.fallback = SeasonalNaive() if "SeasonalNaive" in globals() else None

    def _get_predictor(self) -> ArtifactPredictor:
        predictor = ArtifactPredictor.from_active_version(
            models_root=self.models_root,
            fallback=self.fallback,
        )
        if predictor is not None:
            return predictor

        # Mock bundle fallback to ensure ArtifactPredictor logic is fully exercised in CI
        class MockBundle:
            version = "mock_v1"

            def predict(self, df):
                import numpy as np

                # Emulate route 5 zero-forcing rule and non-negative prediction
                return np.where(df["route"] == 5, 0.0, 100.0)

        return ArtifactPredictor(bundle=MockBundle(), fallback=self.fallback)

    def test_from_active_version(self):
        """Must load active bundle (baseline_v1) successfully."""
        active = get_active_version(models_root=self.models_root)
        if not active or not (self.models_root / active).is_dir():
            self.skipTest(f"Active model bundle not found in {self.models_root}")

        predictor = ArtifactPredictor.from_active_version(
            models_root=self.models_root,
            fallback=self.fallback,
        )
        self.assertIsNotNone(predictor, "Failed to load active version predictor")
        self.assertEqual(predictor.method, "tram_bundle")
        self.assertEqual(predictor.version, active)

    def test_hourly_prediction_generation(self):
        """Predictor must generate hourly predictions with route 5 zero-forced."""
        predictor = self._get_predictor()
        self.assertIsNotNone(predictor)

        series = (
            SpatialKey(level=SpatialLevel.ROUTE, route_id="1"),
            SpatialKey(level=SpatialLevel.ROUTE, route_id="5"),
            SpatialKey(level=SpatialLevel.ROUTE, route_id="17"),
        )
        start = aware(datetime(2025, 11, 1, 0, 0, tzinfo=UTC))
        end = aware(datetime(2025, 11, 1, 6, 0, tzinfo=UTC))  # 6 hours
        window = Interval(start, end)
        as_of = start

        predictions = predictor.predict(
            history=(),
            series=series,
            window=window,
            horizon=Horizon.DAY,
            resolution=Resolution.HOUR,
            as_of=as_of,
        )

        # 6 hours * 3 routes = 18 predictions
        self.assertEqual(len(predictions), 18)

        # Verify Route 5 is strictly zero
        r5_preds = [p for p in predictions if p.spatial.route_id == "5"]
        self.assertEqual(len(r5_preds), 6)
        for p in r5_preds:
            self.assertEqual(p.value, 0.0)

        # Verify all values are non-negative
        for p in predictions:
            self.assertIsNotNone(p.value)
            self.assertGreaterEqual(p.value, 0.0)

    def test_fallback_on_daily_resolution(self):
        """Resolution != HOUR must safely delegate to fallback predictor."""
        predictor = self._get_predictor()
        self.assertIsNotNone(predictor)

        from tram.domain.time import MOSCOW, forecast_window

        series = (SpatialKey(level=SpatialLevel.ROUTE, route_id="1"),)
        start = datetime(2025, 11, 1, 0, 0, tzinfo=MOSCOW)
        window = forecast_window(start, Horizon.MONTH, Resolution.DAY)
        as_of = start

        predictions = predictor.predict(
            history=(),
            series=series,
            window=window,
            horizon=Horizon.MONTH,
            resolution=Resolution.DAY,
            as_of=as_of,
        )
        self.assertEqual(len(predictions), 30)  # 30 days in November
        self.assertEqual(predictions[0].missing_reason, "reference_observation_unavailable")


if __name__ == "__main__":
    unittest.main()
