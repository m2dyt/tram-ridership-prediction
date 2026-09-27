"""Unit tests for model bundle export, loading, verification, and tamper detection."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from ml.training.tram.bundle import (
    BundleError,
    ChecksumMismatchError,
    export_model_bundle,
    get_active_version,
    load_model_bundle,
    set_active_version,
)
from ml.training.tram.features import generate_full_grid


class TestModelBundle(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.models_root = Path(self.temp_dir.name)

        # Create dummy models and profiles
        self.dummy_profiles = {
            "prof_route_dow_hour": pd.DataFrame(
                [
                    {
                        "route": 1,
                        "dow_effective": 0,
                        "hour": 12,
                        "hist_mean_route_dow_hour": 50.0,
                        "hist_median_route_dow_hour": 50.0,
                        "hist_std_route_dow_hour": 5.0,
                    }
                ]
            ),
            "prof_route_dow_hour_nonsummer": pd.DataFrame(
                [
                    {
                        "route": 1,
                        "dow_effective": 0,
                        "hour": 12,
                        "hist_median_nonsummer_route_dow_hour": 45.0,
                    }
                ]
            ),
            "prof_route_dow_hour_recent": pd.DataFrame(),
            "prof_night_q95": pd.DataFrame(),
            "prof_route_dayoff_hour": pd.DataFrame(),
            "prof_route_hour": pd.DataFrame(),
            "prof_route": pd.DataFrame(),
            "closed_weekend_routes": [],
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_export_and_load_bundle(self):
        """Bundle must serialize and deserialize properly with valid checksum."""
        version = "test_v1"
        export_model_bundle(
            version=version,
            models=None,
            profiles=self.dummy_profiles,
            metrics={"wape": 0.05, "wape_score": 0.95, "mae": 10.0},
            config={"model_type": "baseline", "use_residual": False},
            models_root=self.models_root,
        )

        bundle = load_model_bundle(version, models_root=self.models_root)
        self.assertEqual(bundle.version, version)
        self.assertEqual(bundle.metrics["wape_score"], 0.95)
        self.assertIn("prof_route_dow_hour", bundle.profiles)

    def test_prevent_accidental_overwrite(self):
        """Exporting to an existing version without overwrite=True must fail."""
        version = "test_v1"
        export_model_bundle(
            version=version,
            models=None,
            profiles=self.dummy_profiles,
            metrics={},
            config={},
            models_root=self.models_root,
        )

        with self.assertRaises(BundleError):
            export_model_bundle(
                version=version,
                models=None,
                profiles=self.dummy_profiles,
                metrics={},
                config={},
                models_root=self.models_root,
                overwrite=False,
            )

    def test_checksum_tamper_detection(self):
        """Corrupting estimator.joblib must trigger ChecksumMismatchError."""
        version = "tamper_test"
        bundle_path = export_model_bundle(
            version=version,
            models=None,
            profiles=self.dummy_profiles,
            metrics={},
            config={},
            models_root=self.models_root,
        )

        # Tamper with estimator.joblib
        est_file = bundle_path / "estimator.joblib"
        est_file.write_bytes(b"tampered-content")

        with self.assertRaises(ChecksumMismatchError):
            load_model_bundle(version, models_root=self.models_root, verify_checksum=True)

    def test_active_version_pointer(self):
        """Setting and reading active version pointer."""
        set_active_version("prod_candidate_v1", models_root=self.models_root)
        active = get_active_version(models_root=self.models_root)
        self.assertEqual(active, "prod_candidate_v1")

    def test_baseline_bundle_predict(self):
        """Test inference execution through loaded baseline bundle."""
        bundle_dir = Path("models/tram/baseline_v1")
        if not bundle_dir.is_dir():
            self.skipTest("models/tram/baseline_v1 not yet created")

        bundle = load_model_bundle("baseline_v1", models_root=Path("models/tram"))
        grid = generate_full_grid("2025-11-01", "2025-11-01", routes=[1, 5, 7])
        preds = bundle.predict(grid)

        self.assertEqual(len(preds), len(grid))
        self.assertTrue((preds >= 0).all())
        # Route 5 must strictly be 0
        r5_preds = preds[grid["route"].values == 5]
        self.assertTrue((r5_preds == 0).all())


if __name__ == "__main__":
    unittest.main()
