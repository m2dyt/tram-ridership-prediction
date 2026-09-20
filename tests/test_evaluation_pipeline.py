import csv
import json

import pytest
from tram.application.evaluation import EvaluateBaseline
from tram.application.publication import PublishDataset
from tram.application.service import ReadService
from tram.domain.errors import DomainError
from tram.infrastructure.bundles import read_bundle
from tram.infrastructure.contract import Contract
from tram.infrastructure.csv_import import COLUMNS, prepare_csv
from tram.infrastructure.database import Base, make_engine, session_factory
from tram.infrastructure.demo import write_demo
from tram.infrastructure.evaluation import SqlEvaluationStore
from tram.infrastructure.publication import SqlDatasetWriter
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SignedCursor
from tram_ml.baseline import SeasonalNaive
from tram_ml.evaluation import score, temporal_folds

from tests.support import NOW, ROOT, FrozenClock


@pytest.mark.parametrize(
    "horizon,origin,count",
    [
        ("day", "2026-09-19T00:00:00+03:00", 24),
        ("month", "2026-08-20T00:00:00+03:00", 31),
        ("year", "2025-09-01T00:00:00+03:00", 12),
    ],
)
def test_baseline_report_is_published_with_full_horizon(tmp_path, horizon, origin, count):
    directory = tmp_path / "demo"
    revision = write_demo(directory, NOW)
    contract = Contract(ROOT / "openapi.yaml")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    clock = FrozenClock()
    manifest, records = read_bundle(directory, contract)
    PublishDataset(SqlDatasetWriter(sessions), clock).execute(manifest, records)
    repo = SqlRepository(sessions)
    reads = ReadService(repo, clock, SignedCursor("c" * 32))
    runner = EvaluateBaseline(
        repo,
        SqlEvaluationStore(sessions, contract),
        reads,
        clock,
        SeasonalNaive(),
        temporal_folds,
        score,
    )
    report = runner.execute(revision, "demo-validations-" + horizon, [origin])
    assert report["folds"][0]["point_count"] == count
    assert report["scores"][0]["sample_count"] == count
    assert report["summary"]["model"]["is_baseline"]
    assert repo.evaluation(report["summary"]["id"]) == report
    with pytest.raises(DomainError):
        runner.execute(revision, "demo-validations-" + horizon, ["2026-09-20T00:00:00+03:00"])
    engine.dispose()


def test_csv_roundtrip_retains_null_not_zero(tmp_path):
    source = tmp_path / "demo"
    write_demo(source, NOW)
    records = [
        json.loads(line) for line in (source / "observations.jsonl").read_text().splitlines()
    ]
    records[0]["point"].update(value=None, missing_reason="source_missing")
    csv_path = tmp_path / "source.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        for record in records:
            p = record["point"]
            writer.writerow(
                {
                    "profile_id": record["profile_id"],
                    "available_at": record["available_at"],
                    **p["spatial"],
                    **{
                        k: p[k]
                        for k in (
                            "interval_start",
                            "interval_end",
                            "value",
                            "value_kind",
                            "estimation_method",
                            "missing_reason",
                        )
                    },
                }
            )
    output = tmp_path / "converted"
    contract = Contract(ROOT / "openapi.yaml")
    assert prepare_csv(source / "manifest.json", csv_path, output, contract) == len(records)
    _, converted = read_bundle(output, contract)
    assert next(converted)["point"]["value"] is None
