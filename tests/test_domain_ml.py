import unittest
from datetime import datetime, timedelta

from tram.domain.errors import DomainError
from tram.domain.series import Observation, SpatialKey, SpatialLevel
from tram.domain.time import Horizon, Interval, Resolution, forecast_window, intervals, parse_time
from tram_ml.baseline import SeasonalNaive
from tram_ml.evaluation import score, temporal_folds
from tram_ml.features import calendar_features


class DomainMLTests(unittest.TestCase):
    def test_calendar_boundaries_and_leap_year(self):
        month = forecast_window(
            parse_time("2024-01-31T00:00:00+03:00"), Horizon.MONTH, Resolution.DAY
        )
        assert month.end == parse_time("2024-02-29T00:00:00+03:00")
        assert len(intervals(month, Resolution.DAY)) == 29
        year = forecast_window(
            parse_time("2024-02-01T00:00:00+03:00"), Horizon.YEAR, Resolution.MONTH
        )
        assert len(intervals(year, Resolution.MONTH)) == 12
        assert year.end == parse_time("2025-02-01T00:00:00+03:00")

    def test_naive_dates_and_misaligned_periods_are_rejected(self):
        with self.assertRaises(DomainError):
            Interval(datetime(2026, 1, 1), datetime(2026, 1, 2))
        with self.assertRaises(DomainError):
            forecast_window(parse_time("2026-09-20T01:00:00+03:00"), Horizon.DAY, Resolution.HOUR)
        with self.assertRaises(DomainError):
            forecast_window(parse_time("2026-09-20T00:00:00+03:00"), Horizon.YEAR, Resolution.MONTH)

    def test_spatial_keys_reject_cross_level_dimensions_and_avoid_collisions(self):
        with self.assertRaises(DomainError):
            SpatialKey(SpatialLevel.ROUTE, "1", stop_id="x", stop_sequence=1)
        with self.assertRaises(DomainError):
            SpatialKey(SpatialLevel.STOP, "1", stop_id="x")
        assert (
            SpatialKey(SpatialLevel.ROUTE_DIRECTION, "a:b", "c").canonical
            != SpatialKey(SpatialLevel.ROUTE_DIRECTION, "a", "b:c").canonical
        )

    def test_baseline_excludes_late_available_history_and_future_facts(self):
        spatial = SpatialKey(SpatialLevel.ROUTE, "r1")
        start = parse_time("2026-09-21T00:00:00+03:00")
        cutoff = start - timedelta(hours=1)
        window = forecast_window(start, Horizon.DAY, Resolution.HOUR)
        observations = []
        for hour in range(24):
            reference = start - timedelta(days=7) + timedelta(hours=hour)
            interval = Interval(reference, reference + timedelta(hours=1))
            availability = interval.end if hour != 1 else start + timedelta(days=1)
            observations.append(Observation(spatial, interval, availability, 10 + hour))
        observations.append(
            Observation(
                spatial,
                Interval(start, start + timedelta(hours=1)),
                start + timedelta(hours=1),
                999,
            )
        )
        result = SeasonalNaive().predict(
            observations, (spatial,), window, Horizon.DAY, Resolution.HOUR, cutoff
        )
        assert len(result) == 24
        assert result[0].value == 10
        assert result[1].value is None and result[1].missing_reason
        assert result[-1].value == 33

    def test_monthly_baseline_reuses_only_reference_week_before_as_of(self):
        spatial = SpatialKey(SpatialLevel.ROUTE, "r1")
        start = parse_time("2026-09-21T00:00:00+03:00")
        window = forecast_window(start, Horizon.MONTH, Resolution.DAY)
        history = [
            Observation(
                spatial,
                Interval(start - timedelta(days=d), start - timedelta(days=d - 1)),
                start,
                float(d),
            )
            for d in range(1, 8)
        ]
        result = SeasonalNaive().predict(
            history, (spatial,), window, Horizon.MONTH, Resolution.DAY, start
        )
        assert len(result) == 30
        assert result[0].value == result[7].value == result[14].value == 7
        assert all(p.reference_start < start for p in result)

    def test_metrics_zero_denominator_missing_and_invalid_values(self):
        assert score([0, 0], [1, 2]).wape is None
        assert score([0, 0], [1, 2]).wape_unavailable_reason == "zero_actual_sum"
        result = score([10, None, 20], [12, 99, 18])
        assert result.sample_count == 2 and result.excluded_count == 1
        assert result.mae == 2 and abs(result.wape - 4 / 30) < 1e-12
        assert score([], []).wape_unavailable_reason == "empty_sample"
        with self.assertRaises(DomainError):
            score([float("nan")], [1])

    def test_annual_validation_requires_full_horizon(self):
        history = Interval(
            parse_time("2024-01-01T00:00:00+03:00"), parse_time("2026-09-01T00:00:00+03:00")
        )
        with self.assertRaisesRegex(DomainError, "Insufficient history"):
            temporal_folds(
                history, [parse_time("2026-01-01T00:00:00+03:00")], Horizon.YEAR, Resolution.MONTH
            )
        (fold,) = temporal_folds(
            history, [parse_time("2025-01-01T00:00:00+03:00")], Horizon.YEAR, Resolution.MONTH
        )
        assert fold.training.end == fold.test.start

    def test_calendar_features_use_moscow_day(self):
        assert calendar_features(parse_time("2026-09-20T22:00:00Z")).weekday == 0
