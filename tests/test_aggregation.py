from datetime import timedelta

import pytest
from tram.domain.aggregation import weighted_occupancy
from tram.domain.time import Interval

from tests.support import NOW
from tests.test_publication import publication as publication


def test_occupancy_is_time_weighted_per_vehicle_and_ratio_uses_own_capacity():
    passages = [
        dict(start=NOW, end=NOW + timedelta(minutes=10), remaining=30, capacity=60, trip_id="a"),
        dict(start=NOW, end=NOW + timedelta(minutes=20), remaining=60, capacity=100, trip_id="b"),
    ]
    window = Interval(NOW, NOW + timedelta(hours=1))
    assert weighted_occupancy(passages, window)[0] == 50
    assert weighted_occupancy(passages, window, True)[0] == pytest.approx((0.5 + 2 * 0.6) / 3)
    assert weighted_occupancy([], window)[0] is None
    passages[0]["capacity"] = None
    assert weighted_occupancy(passages, window, True)[:2] == (None, "capacity_unavailable")


def test_bucket_boundary_splits_passage_weight():
    passages = [
        dict(
            start=NOW - timedelta(minutes=10),
            end=NOW + timedelta(minutes=10),
            remaining=30,
            capacity=60,
            trip_id="a",
        )
    ]
    assert weighted_occupancy(passages, Interval(NOW, NOW + timedelta(hours=1)))[0] == 30


def test_journal_exports_publishable_estimated_segment_bundle(publication, tmp_path):
    from tram.application.occupancy import OccupancyService
    from tram.application.occupancy_export import export_occupancy
    from tram.application.service import ReadService
    from tram.infrastructure.bundles import read_bundle
    from tram.infrastructure.contract import Contract, strict_json
    from tram.infrastructure.demo import write_demo
    from tram.infrastructure.repository import SqlRepository
    from tram.infrastructure.runtime import SignedCursor
    from tram.infrastructure.trips import SqlTripStore

    from tests.support import ROOT, FrozenClock

    publisher, sessions = publication
    directory = tmp_path / "demo"
    write_demo(directory, NOW)
    publisher.execute(*read_bundle(directory, Contract(ROOT / "openapi.yaml")))
    clock = FrozenClock()
    reads = ReadService(SqlRepository(sessions), clock, SignedCursor("c" * 32))
    service = OccupancyService(SqlTripStore(sessions), clock, reads)
    plan = strict_json((directory / "trip-plan.json").read_bytes())
    service.create(plan)
    for line in (directory / "trip-events.jsonl").read_text().splitlines():
        service.apply(plan["trip_id"], strict_json(line))
    manifest, records = export_occupancy(
        service,
        reads,
        [plan["trip_id"]],
        "estimated-data-v1",
        "2026-09-19T12:00:00+03:00",
        "2026-09-19T14:00:00+03:00",
        "hour",
        "occupancy",
    )
    values = list(records)
    assert [v["point"]["value"] for v in values] == [24, None, 30, None, 18, None]
    assert all(v["point"]["value_kind"] == "estimated" for v in values)
    assert publisher.execute(manifest, iter(values))
