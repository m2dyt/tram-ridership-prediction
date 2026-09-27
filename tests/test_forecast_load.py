import math

import pytest
from tram.application.errors import ApplicationError
from tram.application.forecast_load import typical_trip_load
from tram.application.service import ForecastService, ReadService
from tram.application.worker import RunWorker
from tram.infrastructure.bundles import read_bundle
from tram.infrastructure.contract import Contract
from tram.infrastructure.demo import write_demo
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SignedCursor
from tram_ml.baseline import SeasonalNaive

from tests.support import NOW, ROOT, FrozenClock
from tests.test_publication import publication as publication

STOPS = [{"sequence": i, "stop_id": f"s{i}"} for i in (1, 2, 3, 4)]


def test_trip_load_balances_passengers_and_clears_the_terminal():
    result = typical_trip_load(STOPS, {1: 80, 2: 40, 3: 16, 4: 99}, NOW, 8, 10, "uniform")
    rows = result["stops"]
    assert [r["boardings"] for r in rows] == [10, 5, 2, 0]
    assert rows[-1]["onboard"] == pytest.approx(0)
    assert math.fsum(r["alightings"] for r in rows) == pytest.approx(17)
    assert result["summary"]["peak_sequence"] in (1, 2)
    assert result["summary"]["boardings_per_trip"] == 17
    assert rows[0]["occupancy_ratio"] == pytest.approx(1.0)
    assert "terminal_boardings_excluded" in result["flags"]


def test_missing_forecast_is_flagged_not_hidden():
    result = typical_trip_load(STOPS, {1: 8, 3: 8}, NOW, 8, None, "short")
    assert result["stops"][1]["boardings"] == 0
    assert result["stops"][0]["occupancy_ratio"] is None
    assert "missing_forecast_points" in result["flags"]


def stop_run(publication, tmp_path):
    publisher, sessions = publication
    write_demo(tmp_path / "demo", NOW)
    contract = Contract(ROOT / "openapi.yaml")
    publisher.execute(*read_bundle(tmp_path / "demo", contract))
    repo, clock = SqlRepository(sessions), FrozenClock()
    reads = ReadService(repo, clock, SignedCursor("c" * 32))
    caps = reads.capabilities({})
    profile = next(p for p in caps["forecast_profiles"] if p["spatial_level"] == "stop")
    run, _ = ForecastService(repo, clock, reads).create(
        {
            "dataset_revision_id": caps["dataset_revision_id"],
            "profile_id": profile["id"],
            "route_ids": profile["route_ids"],
            "as_of": profile["allowed_as_of_end"],
            "forecast_start": profile["forecast_start_min"],
        },
        "operator",
        "trip-load",
    )
    assert RunWorker(repo, clock, SeasonalNaive()).execute_one()
    return reads, reads.get_run(run["id"]), contract


def test_forecast_trip_load_endpoint_logic(publication, tmp_path):
    reads, run, contract = stop_run(publication, tmp_path)
    route = run["route_ids"][0]
    query = {"route_id": [route], "interval_start": run["forecast_start"], "capacity": 20}
    result = reads.trip_load(run["id"], query)
    contract.validate("ForecastTripLoad", result)
    hourly = reads.aggregate(
        run["id"],
        {
            "route_id": [route],
            "from": run["forecast_start"],
            "to": result["interval_end"],
            "stop_sequence_to": 3,
        },
    )["summary"]["value"]
    assert result["summary"]["boardings_per_trip"] == pytest.approx(hourly / 8)
    assert result["direction_id"] == "demo-outbound"
    assert result["stops"][-1]["onboard"] == pytest.approx(0)
    assert "estimated_from_forecast" in result["quality"]["flags"]
    for invalid in (
        {**query, "interval_start": "2000-01-01T00:00:00+03:00"},
        {**query, "route_id": []},
        {**query, "direction_id": "unknown"},
    ):
        with pytest.raises(ApplicationError):
            reads.trip_load(run["id"], invalid)
