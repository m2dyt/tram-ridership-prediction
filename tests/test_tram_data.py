"""Unit tests for tram_data module: schema validation, key constraints, and quality reporting."""

import json
import unittest
from pathlib import Path

import pandas as pd

from ml.training.tram_data import (
    ALL_ROUTES,
    InvalidKeyError,
    SchemaValidationError,
    TemporalOverlapError,
    generate_quality_report,
    validate_labels_df,
)


class TestTramData(unittest.TestCase):
    def setUp(self):
        self.valid_train_df = pd.DataFrame({
            "route": [1, 1, 17],
            "date": ["2025-01-01", "2025-01-01", "2025-02-15"],
            "hour": [8, 9, 12],
            "boardings": [100, 150, 320],
        })

    def test_valid_dataframe_passes(self):
        # Should not raise
        validate_labels_df(self.valid_train_df, expected_split="train")

    def test_missing_column_raises_schema_error(self):
        bad_df = self.valid_train_df.drop(columns=["hour"])
        with self.assertRaises(SchemaValidationError):
            validate_labels_df(bad_df)

    def test_null_value_raises_schema_error(self):
        bad_df = self.valid_train_df.copy()
        bad_df.loc[0, "boardings"] = None
        with self.assertRaises(SchemaValidationError):
            validate_labels_df(bad_df)

    def test_negative_boardings_raises_schema_error(self):
        bad_df = self.valid_train_df.copy()
        bad_df.loc[0, "boardings"] = -5
        with self.assertRaises(SchemaValidationError):
            validate_labels_df(bad_df)

    def test_invalid_route_raises_invalid_key_error(self):
        bad_df = self.valid_train_df.copy()
        bad_df.loc[0, "route"] = 999  # Not in ALL_ROUTES
        with self.assertRaises(InvalidKeyError):
            validate_labels_df(bad_df)

    def test_invalid_hour_raises_invalid_key_error(self):
        bad_df = self.valid_train_df.copy()
        bad_df.loc[0, "hour"] = 25  # > 23
        with self.assertRaises(InvalidKeyError):
            validate_labels_df(bad_df)

    def test_duplicate_primary_key_raises_invalid_key_error(self):
        dup_df = pd.DataFrame({
            "route": [1, 1],
            "date": ["2025-01-01", "2025-01-01"],
            "hour": [8, 8],
            "boardings": [100, 105],
        })
        with self.assertRaises(InvalidKeyError):
            validate_labels_df(dup_df)

    def test_temporal_overlap_raises_error(self):
        # Train split only allows 2025-01-01 to 2025-08-31
        leak_df = pd.DataFrame({
            "route": [1],
            "date": ["2025-09-15"],  # September leaked into train
            "hour": [10],
            "boardings": [200],
        })
        with self.assertRaises(TemporalOverlapError):
            validate_labels_df(leak_df, expected_split="train")

    def test_quality_report_structure(self):
        report = generate_quality_report(self.valid_train_df, split_name="sample")
        self.assertEqual(report["total_rows"], 3)
        self.assertEqual(report["total_boardings"], 570)
        self.assertIn("per_route_summary", report)
        self.assertTrue(report["per_route_summary"]["1"]["active"])
        self.assertFalse(report["per_route_summary"]["5"]["active"])

    def test_manifest_and_provenance_files_exist(self):
        manifest_p = Path("data/training/tram-competition-v1/manifest.json")
        provenance_p = Path("sources/tram-competition-2025/provenance.json")

        self.assertTrue(manifest_p.is_file(), "data/training/tram-competition-v1/manifest.json is missing")
        self.assertTrue(provenance_p.is_file(), "sources/tram-competition-2025/provenance.json is missing")

        with manifest_p.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["dataset_id"], "tram-competition-v1")
        self.assertEqual(manifest["routes"], ALL_ROUTES)

        with provenance_p.open("r", encoding="utf-8") as f:
            provenance = json.load(f)
        self.assertIn("files", provenance)
        self.assertIn("train.csv", provenance["files"])


if __name__ == "__main__":
    unittest.main()
