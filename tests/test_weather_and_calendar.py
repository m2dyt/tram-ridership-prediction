"""Unit tests for weather and calendar data pipelines."""

import unittest
from pathlib import Path

import pandas as pd

from ml.training.tram.features import (
    WEATHER_FEATURE_COLS,
    attach_weather_features,
    generate_full_grid,
)


class TestWeatherAndCalendar(unittest.TestCase):
    def test_calendar_file_integrity(self):
        """Calendar table must have exactly 365 days and valid schema."""
        cal_path = Path("data/calendar_2025.csv")
        if not cal_path.is_file():
            self.skipTest(f"Missing {cal_path} (generate via scripts/generate_calendar_2025.py)")

        df = pd.read_csv(cal_path)
        self.assertEqual(len(df), 365)
        expected_cols = [
            "date",
            "dayofweek",
            "month",
            "day",
            "is_weekend",
            "is_holiday",
            "is_preholiday",
            "is_workday",
            "is_day_off",
            "is_transferred_workday",
            "dow_effective",
        ]
        for col in expected_cols:
            self.assertIn(col, df.columns)
        self.assertEqual(df.isna().sum().sum(), 0)

        # 2025-11-01 must be working Saturday (pre-holiday)
        nov1 = df[df["date"] == "2025-11-01"].iloc[0]
        self.assertEqual(nov1["is_workday"], 1)
        self.assertEqual(nov1["is_preholiday"], 1)
        self.assertEqual(nov1["dow_effective"], 4)

    def test_weather_file_integrity(self):
        """Weather table must cover full 2025 year: 8760 hours without nulls."""
        weather_path = Path("data/weather_hourly_2025.csv")
        if not weather_path.is_file():
            self.skipTest(f"Missing {weather_path} (fetch via scripts/fetch_weather_2025.py)")

        df = pd.read_csv(weather_path)
        # 365 days * 24 hours = 8760
        self.assertEqual(len(df), 8760)

        for col in WEATHER_FEATURE_COLS:
            self.assertIn(col, df.columns)
            self.assertEqual(df[col].isna().sum(), 0, f"Nulls found in {col}")

        # Check realistic temperature bounds for Moscow
        self.assertGreater(df["temperature_2m"].min(), -35.0)
        self.assertLess(df["temperature_2m"].max(), 40.0)

    def test_attach_weather_features(self):
        """attach_weather_features must correctly join and fill defaults."""
        grid = generate_full_grid("2025-11-01", "2025-11-01", routes=[1, 7])
        df_attached = attach_weather_features(grid)

        for col in WEATHER_FEATURE_COLS:
            self.assertIn(col, df_attached.columns)
            self.assertEqual(df_attached[col].isna().sum(), 0)

        # November 1st, 2025 temperature must be valid
        self.assertEqual(len(df_attached), 48)  # 2 routes * 24 hours


if __name__ == "__main__":
    unittest.main()
