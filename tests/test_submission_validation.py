"""Unit tests for submission validator (scripts/validate_submission.py)."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.validate_submission import validate_submission


class TestSubmissionValidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        # Baseline files
        self.baseline_path = Path("ml/predictions/baseline/submission_best_baseline.csv")
        self.aligned_path = Path("ml/predictions/baseline/submission_best_baseline_aligned.csv")
        self.sample_path = Path("dataset/test_submission.csv")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_baseline_passes_validation(self):
        """Official best baseline must pass all critical validation rules."""
        if not self.baseline_path.exists():
            self.skipTest(f"Baseline file {self.baseline_path} not found")

        result = validate_submission(
            self.baseline_path,
            sample_path=self.sample_path if self.sample_path.exists() else None,
        )
        self.assertTrue(result["success"], f"Validation failed with errors: {result['errors']}")
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(result["stats"]["total_predicted_passengers"], 12712823)

    def test_aligned_baseline_matches_sample_order(self):
        """Aligned baseline must match official test sample order with 0 warnings."""
        if not self.aligned_path.exists() or not self.sample_path.exists():
            self.skipTest("Aligned or sample submission not found")

        result = validate_submission(
            self.aligned_path,
            sample_path=self.sample_path,
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["stats"].get("sample_exact_order_match", False))
        self.assertEqual(len(result["warnings"]), 0)

    def test_catches_route_5_non_zero(self):
        """Validator must fail if route 5 has any non-zero prediction."""
        if not self.aligned_path.exists():
            self.skipTest("Aligned baseline file not found")

        df = pd.read_csv(self.aligned_path, sep=";")
        # Inject non-zero into route 5
        mask_r5 = df["route"] == 5
        df.loc[mask_r5, "prediction"] = 42

        bad_file = self.temp_path / "bad_route5.csv"
        df.to_csv(bad_file, sep=";", index=False)

        result = validate_submission(bad_file)
        self.assertFalse(result["success"])
        self.assertTrue(any("Route 5 rule violated" in err for err in result["errors"]))

    def test_catches_negative_predictions(self):
        """Validator must fail on negative predictions."""
        if not self.aligned_path.exists():
            self.skipTest("Aligned baseline file not found")

        df = pd.read_csv(self.aligned_path, sep=";")
        df.loc[0, "prediction"] = -10

        bad_file = self.temp_path / "negative.csv"
        df.to_csv(bad_file, sep=";", index=False)

        result = validate_submission(bad_file)
        self.assertFalse(result["success"])
        self.assertTrue(any("negative" in err.lower() for err in result["errors"]))

    def test_catches_wrong_delimiter(self):
        """Validator must fail if comma is used instead of semicolon."""
        if not self.aligned_path.exists():
            self.skipTest("Aligned baseline file not found")

        df = pd.read_csv(self.aligned_path, sep=";")
        bad_file = self.temp_path / "comma_delim.csv"
        df.to_csv(bad_file, sep=",", index=False)

        result = validate_submission(bad_file)
        self.assertFalse(result["success"])
        self.assertTrue(any("delimiter" in err.lower() for err in result["errors"]))

    def test_catches_missing_rows(self):
        """Validator must fail if row count is not exactly 14640."""
        if not self.aligned_path.exists():
            self.skipTest("Aligned baseline file not found")

        df = pd.read_csv(self.aligned_path, sep=";")
        df = df.iloc[:-10]  # remove 10 rows

        bad_file = self.temp_path / "missing_rows.csv"
        df.to_csv(bad_file, sep=";", index=False)

        result = validate_submission(bad_file)
        self.assertFalse(result["success"])
        self.assertTrue(any("Row count mismatch" in err for err in result["errors"]))


if __name__ == "__main__":
    unittest.main()
