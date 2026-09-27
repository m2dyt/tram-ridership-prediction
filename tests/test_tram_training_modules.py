"""Unit tests for modular tram training components (ml/training/tram/)."""

import unittest

import numpy as np
import pandas as pd

from ml.training.tram.baseline import (
    BASE_PROFILE_COL,
    attach_historical_profiles,
    calculate_historical_profiles,
    predict_seasonal_baseline,
)
from ml.training.tram.evaluation import (
    compute_wape_metrics,
)
from ml.training.tram.features import (
    add_calendar_features,
    generate_full_grid,
)
from ml.training.tram.submission import format_submission


class TestTramTrainingModules(unittest.TestCase):
    def test_generate_full_grid(self):
        """Test full Cartesian grid generation."""
        routes = [1, 5, 7]
        grid = generate_full_grid("2025-11-01", "2025-11-02", routes=routes)
        # 2 days * 24 hours * 3 routes = 144 rows
        self.assertEqual(len(grid), 144)
        self.assertEqual(set(grid["route"].unique()), set(routes))
        self.assertEqual(set(grid["hour"].unique()), set(range(24)))
        self.assertEqual(sorted(grid["date"].unique()), ["2025-11-01", "2025-11-02"])

    def test_calendar_features(self):
        """Test calendar and Russian holiday feature engineering."""
        df = pd.DataFrame(
            [
                {"date": "2025-01-01", "hour": 12, "route": 1},  # New Year holiday
                {"date": "2025-01-15", "hour": 8, "route": 1},  # Regular Wednesday workday
                {"date": "2025-11-01", "hour": 18, "route": 1},  # Working Saturday (pre-holiday)
            ]
        )
        df_cal = add_calendar_features(df)

        # 2025-01-01 is holiday -> is_holiday=1, dow_effective=6 (Sunday schedule)
        row_ny = df_cal[df_cal["date"] == "2025-01-01"].iloc[0]
        self.assertEqual(row_ny["is_holiday"], 1)
        self.assertEqual(row_ny["is_workday"], 0)
        self.assertEqual(row_ny["dow_effective"], 6)

        # 2025-01-15 is regular workday
        row_reg = df_cal[df_cal["date"] == "2025-01-15"].iloc[0]
        self.assertEqual(row_reg["is_holiday"], 0)
        self.assertEqual(row_reg["is_workday"], 1)
        self.assertEqual(row_reg["is_morning_peak"], 1)

        # 2025-11-01 is preholiday Saturday -> dow_effective=4 (Friday schedule)
        row_pre = df_cal[df_cal["date"] == "2025-11-01"].iloc[0]
        self.assertEqual(row_pre["is_preholiday"], 1)
        self.assertEqual(row_pre["dow_effective"], 4)

    def test_wape_metrics_calculation(self):
        """Test WAPE and competition WAPE-score calculation."""
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 190.0, 300.0])
        m = compute_wape_metrics(y_true, y_pred)

        # sum_y = 600, sum_abs_err = 10 + 10 + 0 = 20
        # WAPE = 20 / 600 = 0.03333...
        # WAPE-score = 1.0 - 0.03333... = 0.96666...
        self.assertAlmostEqual(m["wape"], 20.0 / 600.0, places=4)
        self.assertAlmostEqual(m["wape_score"], 1.0 - (20.0 / 600.0), places=4)
        self.assertAlmostEqual(m["mae"], 20.0 / 3.0, places=4)

    def test_wape_metrics_all_zeros(self):
        """WAPE for empty or all-zero target should return 0 WAPE and 1.0 score."""
        y_true = np.array([0.0, 0.0])
        y_pred = np.array([0.0, 0.0])
        m = compute_wape_metrics(y_true, y_pred)
        self.assertEqual(m["wape"], 0.0)
        self.assertEqual(m["wape_score"], 1.0)

    def test_historical_profiles_and_baseline(self):
        """Test profile calculation and attachment pipeline."""
        grid = generate_full_grid("2025-01-01", "2025-01-05", routes=[1, 5])
        grid["boardings"] = 50.0
        grid.loc[grid["route"] == 5, "boardings"] = 0.0
        grid = add_calendar_features(grid)

        profiles = calculate_historical_profiles(grid)
        self.assertIn("prof_route_dow_hour", profiles)
        self.assertIn("prof_route_dow_hour_nonsummer", profiles)

        attached = attach_historical_profiles(grid, profiles)
        self.assertIn(BASE_PROFILE_COL, attached.columns)

        preds = predict_seasonal_baseline(attached)
        self.assertEqual(len(preds), len(grid))
        # Route 5 must be zero
        r5_preds = preds[attached["route"].values == 5]
        self.assertTrue((r5_preds == 0).all())

    def test_format_submission_rules(self):
        """Test submission formatter compliance with competition rules."""
        grid_sub = generate_full_grid("2025-11-01", "2025-11-01", routes=[1, 5, 7])
        preds = np.array([100.5, -5.0, 50.0] * 24)  # has floats and negative

        sub = format_submission(grid_sub, preds)
        self.assertEqual(list(sub.columns), ["route", "date", "hour", "prediction"])
        # All predictions must be integers
        self.assertEqual(sub["prediction"].dtype, int)
        # All predictions >= 0
        self.assertTrue((sub["prediction"] >= 0).all())
        # Route 5 must be strictly 0
        r5_sub = sub[sub["route"] == 5]
        self.assertTrue((r5_sub["prediction"] == 0).all())


if __name__ == "__main__":
    unittest.main()
