import copy
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from tram.application.errors import ApplicationError
from tram.application.publication import PublishDataset
from tram.application.service import ForecastService, ReadService
from tram.application.worker import RunWorker
from tram.infrastructure.bundles import read_bundle
from tram.infrastructure.contract import Contract
from tram.infrastructure.database import (
    Base,
    DatasetRow,
    NetworkRow,
    ObservationRow,
    make_engine,
    session_factory,
)
from tram.infrastructure.demo import write_demo
from tram.infrastructure.publication import SqlDatasetWriter
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SignedCursor
from tram_ml.baseline import SeasonalNaive

from tests.support import NOW, ROOT, FrozenClock, fixture_bundle


@pytest.fixture
def publication():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    yield PublishDataset(SqlDatasetWriter(sessions), FrozenClock()), sessions
    engine.dispose()


def test_immutable_revision_and_idempotent_import(publication):
    publisher, sessions = publication
    manifest, records = fixture_bundle()
    assert publisher.execute(manifest, iter(records))
    assert publisher.execute(manifest, iter(records)) is False
    changed = copy.deepcopy(records)
    changed[-1]["point"]["value"] += 1
    with pytest.raises(ApplicationError, match="different content"):
        publisher.execute(manifest, iter(changed))
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(DatasetRow)) == 1
        assert session.scalar(select(func.count()).select_from(ObservationRow)) == len(records)


@pytest.mark.parametrize(
    "fault", ["duplicate", "gap", "incomplete", "future", "unknown_series", "wrong_unit"]
)
def test_invalid_publication_rolls_back_everything(publication, fault):
    publisher, sessions = publication
    manifest, records = fixture_bundle()
    if fault == "duplicate":
        records.append(records[-1])
    elif fault == "gap":
        records.pop(10)
    elif fault == "incomplete":
        records.pop()
    elif fault == "future":
        records[-1]["available_at"] = (NOW + timedelta(days=1)).isoformat()
    elif fault == "unknown_series":
        records[-1]["profile_id"] = "missing"
    else:
        manifest["capabilities"]["observation_profiles"][0]["unit"] = "passengers"
    with pytest.raises(ApplicationError):
        publisher.execute(manifest, iter(records))
    with sessions() as session:
        for table in (NetworkRow, DatasetRow, ObservationRow):
            assert session.scalar(select(func.count()).select_from(table)) == 0


def test_generated_demo_publishes_and_predicts_all_horizons(publication, tmp_path):
    publisher, sessions = publication
    directory = tmp_path / "demo"
    write_demo(directory, NOW)
    with pytest.raises(FileExistsError):
        write_demo(directory, NOW)
    contract = Contract(ROOT / "openapi.yaml")
    manifest, records = read_bundle(directory, contract)
    assert publisher.execute(manifest, records)
    repository, clock = SqlRepository(sessions), FrozenClock()
    reads = ReadService(repository, clock, SignedCursor("s" * 32))
    service = ForecastService(repository, clock, reads)
    from tram.infrastructure.contract import strict_json

    for horizon in ("day", "month", "year"):
        command = strict_json((directory / f"request-{horizon}.json").read_bytes())
        run, _ = service.create(command, "operator", "demo-test-" + horizon)
        assert RunWorker(repository, clock, SeasonalNaive()).execute_one()
        completed = repository.run(run["id"])
        contract.validate("ForecastRun", completed)
        assert completed["source_mode"] == "demo"
        assert completed["status"] == "succeeded"
        assert completed["quality"]["coverage_ratio"] == 1
