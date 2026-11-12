"""Service model: production calendar, fresh profiles, holdout choice, intervals, serving."""

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from tram.application.models import select_model
from tram.application.worker import RunWorker
from tram.domain.errors import DomainError
from tram.domain.series import Interval, Observation, Prediction, SpatialKey, SpatialLevel
from tram.domain.time import MOSCOW, Horizon, Resolution, forecast_window
from tram.infrastructure.ml.artifact_predictor import ArtifactPredictor
from tram.infrastructure.ml.model_catalog import FileModelCatalog
from tram.infrastructure.ml.model_registry import read_model_metadata

from ml.training.tram.adaptive import (
    complete_grid,
    interval_bounds,
    prepare,
    time_aware_frame,
    train_service_model,
)
from ml.training.tram.calendar import calendar_covers, day_info
from ml.training.tram.features import HOLIDAYS_2025, PRE_HOLIDAYS_2025, add_calendar_features
from ml.training.tram.service import export_service_bundles

# --- production calendar -------------------------------------------------------------


def _days(year):
    start = date(year, 1, 1)
    return [start + timedelta(days=i) for i in range((date(year + 1, 1, 1) - start).days)]


def test_calendar_reproduces_the_checked_2025_lists():
    days = _days(2025)
    assert {d.isoformat() for d in days if day_info(d)[0]} == HOLIDAYS_2025
    assert {d.isoformat() for d in days if day_info(d)[1]} == PRE_HOLIDAYS_2025


def test_calendar_knows_2026_and_2027_holidays_and_working_saturdays():
    assert day_info(date(2026, 1, 9))[0] == 1  # New Year break lasts to 11 January 2026
    assert day_info(date(2026, 5, 11))[0] == 1  # transferred Victory Day weekday
    assert day_info(date(2026, 1, 12)) == (0, 0, 0)
    assert day_info(date(2027, 2, 20)) == (0, 1, 1)  # working, shortened Saturday
    frame = add_calendar_features(
        pd.DataFrame({"date": ["2027-02-20", "2026-05-11"], "hour": [8, 8]})
    )
    assert frame["dow_effective"].tolist() == [4, 6]
    assert frame["is_workday"].tolist() == [1, 0]


def test_calendar_outside_the_table_falls_back_to_weekends():
    assert not calendar_covers(["2031-01-01"])
    assert day_info(date(2031, 3, 15)) == (0, 0, 0)  # an ordinary Saturday off
    assert day_info(date(2031, 1, 6))[0] == 1  # 1-8 January are holidays by law
    assert calendar_covers(["2026-03-09"])


# --- adaptive training ---------------------------------------------------------------


def synthetic_labels(start="2025-01-01", end="2025-06-30", seed=0):
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    rows = []
    shape = np.array(
        [
            0,
            0,
            0,
            0,
            0,
            5,
            40,
            120,
            160,
            90,
            60,
            55,
            60,
            60,
            65,
            80,
            120,
            170,
            150,
            90,
            60,
            40,
            20,
            5,
        ]
    )
    for route, scale in ((1, 1.0), (7, 0.6), (5, 0.4)):
        for day in days:
            weekend = 0.6 if day.dayofweek >= 5 else 1.0
            closed = route == 5 and day >= pd.Timestamp("2025-04-01")
            for hour in range(24):
                value = 0.0 if closed else shape[hour] * scale * weekend * rng.uniform(0.9, 1.1)
                if value > 0:
                    rows.append((route, day.strftime("%Y-%m-%d"), hour, round(value)))
    return pd.DataFrame(rows, columns=["route", "date", "hour", "boardings"])


def test_profile_features_never_look_into_the_future():
    labels = synthetic_labels()
    full = prepare(complete_grid(labels))
    before = time_aware_frame(full, "2025-03-03", "2025-03-10")
    changed = full.copy()
    changed.loc[changed["d"] >= "2025-03-03", "boardings"] *= 10
    after = time_aware_frame(changed, "2025-03-03", "2025-03-10")
    columns = ["long", "recent", "recent_dayoff", "std", "ratio", "base"]
    pd.testing.assert_frame_equal(before[columns], after[columns])


def test_service_training_checks_on_a_holdout_and_closes_inactive_routes():
    result = train_service_model(synthetic_labels(), holdout_weeks=4)
    holdout = result.metrics["holdout"]
    assert holdout["start"] == "2025-06-03" and holdout["end"] == "2025-07-01"
    chosen = holdout["model_wape"] if result.use_model else holdout["base_wape"]
    assert result.metrics["overall"]["wape"] == pytest.approx(chosen)
    assert (result.final_model is not None) == result.use_model
    assert result.metrics["per_route"]["5"]["sum_y"] == 0
    assert set(result.intervals["quantiles"]) == {"night", "day", "peak"}
    assert 0 < result.intervals["check_coverage"] <= 1


def test_interval_always_contains_the_forecast():
    values = np.array([0.0, 10.0, 200.0])
    quantiles = {band: {"low": 5.0, "high": -3.0} for band in ("night", "day", "peak")}
    lower, upper = interval_bounds(values, [3, 12, 8], quantiles)
    assert np.all(lower <= values) and np.all(values <= upper)
    assert lower[0] == upper[0] == 0


# --- bundles and serving -------------------------------------------------------------


@pytest.fixture(scope="module")
def service_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("models")
    export_service_bundles(synthetic_labels(), "svc", root, holdout_weeks=4, set_active=True)
    return root


def test_service_bundles_pass_the_registry_and_serve_stops(service_root):
    assert read_model_metadata(service_root / "svc")["config"]["recipe"] == "adaptive_v2"
    check = read_model_metadata(service_root / "svc-check")["config"]
    assert check["training_history_end"] == check["holdout_start"]
    bundle = FileModelCatalog(service_root).active_bundle()
    assert bundle["status"] == "ok" and bundle["spatial_levels"] == ["route", "stop"]
    assert "5" in bundle["routes"]
    as_of = datetime(2025, 7, 1, tzinfo=MOSCOW)
    profile = {"resolution": "hour", "spatial_level": "stop", "id": "stops"}
    model, warnings = select_model(
        profile=profile,
        route_ids=["1"],
        as_of=as_of,
        dataset_models=[],
        bundle=bundle,
        fallback_to_seasonal_naive=True,
    )
    assert model["version"] == "svc" and warnings == []


def _observations(labels, key):
    out = []
    for row in labels.itertuples(index=False):
        start = datetime.fromisoformat(f"{row.date}T{row.hour:02d}:00:00").replace(tzinfo=MOSCOW)
        end = start + timedelta(hours=1)
        out.append(Observation(key, Interval(start, end), end, float(row.boardings)))
    return out


def test_route_and_stop_forecasts_with_intervals(service_root):
    predictor = ArtifactPredictor.from_version(service_root, "svc")
    assert predictor.joint_route_series
    labels = synthetic_labels()
    start = datetime(2025, 7, 1, tzinfo=MOSCOW)
    window = forecast_window(start, Horizon.DAY, Resolution.HOUR)

    route_key = SpatialKey(SpatialLevel.ROUTE, "1")
    route_history = _observations(labels[labels.route == 1], route_key)
    routes = predictor.predict(
        route_history, (route_key,), window, Horizon.DAY, Resolution.HOUR, start
    )
    assert len(routes) == 24 and max(p.value for p in routes) > 100
    for p in routes:
        band = p.prediction_interval
        assert band["lower"] <= p.value <= band["upper"] and band["nominal_coverage"] == 0.8

    closed = SpatialKey(SpatialLevel.ROUTE, "5")
    zero = predictor.predict(
        _observations(labels[labels.route == 5], closed),
        (closed,),
        window,
        Horizon.DAY,
        Resolution.HOUR,
        start,
    )
    assert all(p.value == 0 for p in zero)

    stops = tuple(SpatialKey(SpatialLevel.STOP, "1", "d1", f"s{i}", i) for i in (1, 2, 3))
    recent = labels[(labels.route == 1) & (labels.date >= "2025-06-17")]
    stop_history = []
    for key, share in zip(stops, (0.5, 0.3, 0.2), strict=True):
        stop_history += _observations(recent.assign(boardings=recent.boardings * share), key)
    by_stop = predictor.predict(
        (*route_history, *stop_history), stops, window, Horizon.DAY, Resolution.HOUR, start
    )
    hour8 = {p.spatial.stop_id: p.value for p in by_stop if p.interval.start.hour == 8}
    route8 = next(p.value for p in routes if p.interval.start.hour == 8)
    assert sum(hour8.values()) == pytest.approx(route8)
    assert hour8["s1"] == pytest.approx(route8 * 0.5, rel=0.02)


def test_bundle_trained_with_weather_is_refused(service_root, tmp_path):
    from ml.training.tram.bundle import load_model_bundle

    bundle = load_model_bundle("svc", models_root=service_root)
    bundle.config = {**bundle.config, "use_weather": True}
    with pytest.raises(ValueError, match="weather"):
        ArtifactPredictor(bundle)


def test_prediction_interval_must_contain_the_value():
    key = SpatialKey(SpatialLevel.ROUTE, "1")
    start = datetime(2025, 7, 1, tzinfo=MOSCOW)
    interval = Interval(start, start + timedelta(hours=1))
    band = {"lower": 5.0, "upper": 9.0, "nominal_coverage": 0.8, "method": "m"}
    with pytest.raises(DomainError):
        Prediction(key, interval, 10.0, None, start, band)
    assert Prediction(key, interval, 7.0, None, start, band).prediction_interval == band


# --- worker grouping -----------------------------------------------------------------


class _Repo:
    def dataset(self, revision):
        return {
            "capabilities": {
                "observation_profiles": [
                    {
                        "id": "stops",
                        "spatial_level": "stop",
                        "metric": "boardings",
                        "resolution": "hour",
                    },
                    {
                        "id": "routes",
                        "spatial_level": "route",
                        "metric": "boardings",
                        "resolution": "hour",
                    },
                ]
            }
        }


class _Joint:
    joint_route_series = True


def test_worker_groups_series_by_route_and_finds_the_route_profile():
    worker = RunWorker(_Repo(), None, {"tram_bundle": _Joint()})
    series = [
        {"spatial": {"level": "stop", "route_id": "1", "stop_id": "a", "stop_sequence": 1}},
        {"spatial": {"level": "stop", "route_id": "7", "stop_id": "b", "stop_sequence": 1}},
        {"spatial": {"level": "stop", "route_id": "1", "stop_id": "c", "stop_sequence": 2}},
    ]
    groups = worker._groups(_Joint(), series)
    assert [[item["spatial"]["stop_id"] for item in group] for group in groups] == [
        ["a", "c"],
        ["b"],
    ]
    assert worker._groups(object(), series) == [[item] for item in series]
    run = {"dataset_revision_id": "r", "profile": {"metric": "boardings", "resolution": "hour"}}
    assert worker._route_profile(run) == "routes"
