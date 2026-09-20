import os
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.schema import CreateSchema, DropSchema
from tram.application.service import ForecastService, ReadService
from tram.application.worker import RunWorker
from tram.infrastructure.database import Base, RunRow, make_engine, session_factory
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SignedCursor
from tram_ml.baseline import SeasonalNaive

from tests.support import FrozenClock, seed_trusted_fixture

pytestmark = pytest.mark.postgres


def test_concurrent_trip_event_is_applied_once(postgres_service):
    from tram.application.occupancy import OccupancyService
    from tram.infrastructure.trips import SqlTripStore

    from tests.test_occupancy import event, plan, seed_trip_network

    service = postgres_service
    seed_trip_network(service.sessions)
    occupancy = OccupancyService(SqlTripStore(service.sessions), service.clock, service.reads)
    occupancy.create(plan())
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: occupancy.apply("trip-test", event(1, 12)), range(2)))
    assert all(result["state"]["remaining"] == 12 for result in results)
    # A newly composed service recovers the committed state and journal.
    restored = OccupancyService(SqlTripStore(service.sessions), service.clock, service.reads)
    assert restored.get("trip-test")["state"]["version"] == 1
    assert len(restored.events("trip-test")["items"]) == 1


@pytest.fixture
def postgres_service():
    url = os.environ.get("TRAM_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TRAM_TEST_DATABASE_URL to run PostgreSQL integration checks")
    engine = make_engine(url)
    schema = "tram_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        sessions = session_factory(isolated)
        seed_trusted_fixture(sessions)
        repository = SqlRepository(sessions)
        clock = FrozenClock()
        reads = ReadService(repository, clock, SignedCursor("test-cursor-" * 4))
        yield SimpleNamespace(
            repository=repository,
            sessions=sessions,
            clock=clock,
            reads=reads,
            forecasts=ForecastService(repository, clock, reads),
            request={
                "dataset_revision_id": "demo-data-v1",
                "profile_id": "demo-validations-stop-day-hour",
                "route_ids": ["demo-route-01"],
                "as_of": "2026-09-20T18:00:00+03:00",
                "forecast_start": "2026-09-21T00:00:00+03:00",
            },
        )
    finally:
        # Only this test's random schema is removed; existing DB tables are untouched.
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def test_postgres_concurrent_idempotency(postgres_service):
    service = postgres_service
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: service.forecasts.create(service.request, "operator", "concurrent-key"),
                range(2),
            )
        )
    assert results[0][0]["id"] == results[1][0]["id"]
    assert sum(created for _, created in results) == 1


def test_postgres_worker_publishes_complete_forecast(postgres_service):
    service = postgres_service
    run, _ = service.forecasts.create(service.request, "operator", "worker-test-key")
    assert RunWorker(service.repository, service.clock, SeasonalNaive()).execute_one()
    result = service.repository.run(run["id"])
    assert result["status"] == "succeeded"
    assert result["point_count"] == 24
    points = service.reads.points(
        run["id"], {"from": result["forecast_start"], "to": result["forecast_end"]}
    )
    assert len(points["items"]) == 24
    assert all(point["value"] is not None for point in points["items"])


def test_postgres_claim_skips_locked_job(postgres_service):
    service = postgres_service
    run, _ = service.forecasts.create(service.request, "operator", "locking-test-key")
    with service.sessions.begin() as holding_session:
        holding_session.execute(select(RunRow).where(RunRow.id == run["id"]).with_for_update())
        started = time.monotonic()
        assert service.repository.claim(service.clock.now(), 30, 3) is None
        assert time.monotonic() - started < 2
    assert service.repository.claim(service.clock.now(), 30, 3) is not None


def test_postgres_concurrent_dataset_publication(postgres_service):
    from tram.application.publication import PublishDataset
    from tram.infrastructure.publication import SqlDatasetWriter

    from tests.support import fixture_bundle

    manifest, records = fixture_bundle()
    manifest["capabilities"]["dataset_revision_id"] = "concurrent-publication"
    publisher = PublishDataset(SqlDatasetWriter(postgres_service.sessions), postgres_service.clock)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: publisher.execute(manifest, iter(records)), range(2)))
    assert sum(results) == 1
    assert postgres_service.repository.dataset("concurrent-publication") is not None
