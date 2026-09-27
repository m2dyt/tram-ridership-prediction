from datetime import timedelta

import pytest
from tram.domain.errors import DomainError
from tram.domain.rollup import ForecastRollup, GroupBy, check_group_by
from tram.domain.series import SpatialKey, SpatialLevel
from tram.domain.time import Interval, Resolution, parse_time

MIDNIGHT = parse_time("2026-09-21T00:00:00+03:00")


def stop(sequence, direction="out"):
    return SpatialKey(SpatialLevel.STOP, "r1", direction, f"s{sequence}", sequence)


def hour(index):
    return Interval(MIDNIGHT + timedelta(hours=index), MIDNIGHT + timedelta(hours=index + 1))


def day_window():
    return Interval(MIDNIGHT, MIDNIGHT + timedelta(days=1))


def test_additive_metric_sums_series_and_intervals_and_finds_peak_hour():
    rollup = ForecastRollup(day_window(), "sum", GroupBy.NONE)
    for index, (a, b) in enumerate([(10, 5), (40, 20), (7, 3)]):
        rollup.add(stop(1), hour(index), a)
        rollup.add(stop(2), hour(index), b)
    result = rollup.result()
    summary = result["summary"]
    assert result["statistic"] == "sum"
    assert summary["value"] == 85
    assert summary["interval_max"] == 60
    assert summary["interval_min"] == 10
    assert summary["interval_mean"] == pytest.approx(85 / 3)
    assert summary["peak_interval_start"] == hour(1).start.isoformat()
    assert (summary["series_count"], summary["interval_count"], summary["point_count"]) == (2, 3, 6)
    assert summary["quality"] == {"status": "ok", "coverage_ratio": 1, "flags": []}
    assert result["groups"] == []


def test_missing_point_is_not_zero_and_lowers_coverage():
    rollup = ForecastRollup(day_window(), "sum", GroupBy.NONE)
    rollup.add(stop(1), hour(0), 10)
    rollup.add(stop(2), hour(0), None)
    summary = rollup.result()["summary"]
    assert summary["value"] == 10
    assert summary["missing_count"] == 1
    assert summary["quality"] == {
        "status": "partial",
        "coverage_ratio": 0.5,
        "flags": ["missing_forecast_points"],
    }


def test_empty_selection_has_no_value():
    summary = ForecastRollup(day_window(), "sum", GroupBy.HOUR).result()["summary"]
    assert summary["value"] is None and summary["point_count"] == 0
    assert summary["quality"] == {
        "status": "missing",
        "coverage_ratio": None,
        "flags": ["empty_selection"],
    }


def test_non_additive_metric_is_duration_weighted_mean_never_sum():
    window = Interval(
        parse_time("2026-01-01T00:00:00+03:00"), parse_time("2026-03-01T00:00:00+03:00")
    )
    rollup = ForecastRollup(window, "vehicle_time_weighted_mean", GroupBy.NONE)
    segment = SpatialKey(SpatialLevel.SEGMENT, "r1", "out", segment_id="g1")
    january = Interval(window.start, parse_time("2026-02-01T00:00:00+03:00"))
    february = Interval(january.end, window.end)
    rollup.add(segment, january, 31)
    rollup.add(segment, february, 28)
    result = rollup.result()
    assert result["statistic"] == "mean"
    assert result["summary"]["value"] == pytest.approx((31 * 31 + 28 * 28) / 59)


def test_time_groups_follow_moscow_calendar_and_are_clipped_by_window():
    window = Interval(MIDNIGHT + timedelta(hours=22), MIDNIGHT + timedelta(days=1, hours=2))
    rollup = ForecastRollup(window, "sum", GroupBy.DAY)
    for index in range(22, 26):
        rollup.add(stop(1), hour(index), 1)
    groups = rollup.result()["groups"]
    assert [(g["interval_start"], g["interval_end"], g["value"]) for g in groups] == [
        (window.start.isoformat(), (MIDNIGHT + timedelta(days=1)).isoformat(), 2),
        ((MIDNIGHT + timedelta(days=1)).isoformat(), window.end.isoformat(), 2),
    ]
    assert all(g["route_id"] is None for g in groups)


def test_spatial_groups_keep_only_their_identifiers():
    rollup = ForecastRollup(day_window(), "sum", GroupBy.DIRECTION)
    rollup.add(stop(1, "out"), hour(0), 3)
    rollup.add(stop(2, "out"), hour(0), 4)
    rollup.add(stop(1, "back"), hour(0), 5)
    groups = rollup.result()["groups"]
    assert [(g["direction_id"], g["stop_id"], g["value"]) for g in groups] == [
        ("back", None, 5),
        ("out", None, 7),
    ]
    by_stop = ForecastRollup(day_window(), "sum", GroupBy.STOP)
    by_stop.add(stop(2), hour(0), 4)
    by_stop.add(stop(1), hour(0), 3)
    assert [g["stop_sequence"] for g in by_stop.result()["groups"]] == [1, 2]


def test_points_outside_window_are_rejected():
    rollup = ForecastRollup(Interval(MIDNIGHT, MIDNIGHT + timedelta(hours=1)), "sum", GroupBy.NONE)
    with pytest.raises(DomainError):
        rollup.add(stop(1), hour(1), 1)


@pytest.mark.parametrize(
    "group_by,resolution,level",
    [
        (GroupBy.HOUR, Resolution.DAY, SpatialLevel.ROUTE),
        (GroupBy.DAY, Resolution.MONTH, SpatialLevel.ROUTE),
        (GroupBy.STOP, Resolution.HOUR, SpatialLevel.ROUTE),
        (GroupBy.SEGMENT, Resolution.HOUR, SpatialLevel.STOP),
        (GroupBy.DIRECTION, Resolution.HOUR, SpatialLevel.ROUTE),
    ],
)
def test_unsupported_groupings_are_rejected(group_by, resolution, level):
    with pytest.raises(DomainError):
        check_group_by(group_by, resolution, level)


@pytest.mark.parametrize(
    "group_by,resolution,level",
    [
        (GroupBy.NONE, Resolution.MONTH, SpatialLevel.ROUTE),
        (GroupBy.HOUR, Resolution.HOUR, SpatialLevel.ROUTE),
        (GroupBy.MONTH, Resolution.DAY, SpatialLevel.ROUTE),
        (GroupBy.ROUTE, Resolution.DAY, SpatialLevel.ROUTE),
        (GroupBy.DIRECTION, Resolution.HOUR, SpatialLevel.STOP),
        (GroupBy.STOP, Resolution.HOUR, SpatialLevel.STOP),
        (GroupBy.SEGMENT, Resolution.HOUR, SpatialLevel.SEGMENT),
    ],
)
def test_supported_groupings_pass(group_by, resolution, level):
    check_group_by(group_by, resolution, level)
