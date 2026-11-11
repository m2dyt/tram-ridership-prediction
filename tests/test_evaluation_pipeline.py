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


class _DoubledModel:
    """A trained model stand-in: twice the seasonal value, with a known interval."""

    def predict(self, history, series, window, horizon, resolution, as_of):
        from tram.domain.series import Prediction

        out = []
        for p in SeasonalNaive().predict(history, series, window, horizon, resolution, as_of):
            if p.value is None:
                out.append(p)
                continue
            band = {
                "lower": 0.0,
                "upper": p.value * 4,
                "nominal_coverage": 0.8,
                "method": "test",
            }
            out.append(Prediction(p.spatial, p.interval, p.value * 2, None, as_of, band))
        return tuple(out)


def _demo_runner(tmp_path, model=None, model_doc=None):
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
        model=model,
        model_doc=model_doc,
    )
    return runner, revision, engine


MODEL_DOC = {
    "id": "svc-check",
    "version": "svc-check",
    "method": "tram_bundle",
    "training_history_end": "2026-09-01T00:00:00+03:00",
    "feature_set_version": "features-test",
    "is_baseline": False,
}


def test_trained_model_is_checked_next_to_the_seasonal_baseline(tmp_path):
    runner, revision, engine = _demo_runner(tmp_path, _DoubledModel(), MODEL_DOC)
    report = runner.execute(revision, "demo-validations-day", ["2026-09-19T00:00:00+03:00"])
    assert report["summary"]["model"]["version"] == "svc-check"
    by_method = {
        s["method"]: s
        for s in report["scores"]
        if s["route_id"] is None and s["demand_slice"] == "all"
    }
    assert by_method["model"]["mae"] != by_method["seasonal_naive"]["mae"]
    assert by_method["model"]["sample_count"] == by_method["seasonal_naive"]["sample_count"]
    assert 0 <= by_method["model"]["interval_coverage"] <= 1
    assert by_method["model"]["mean_interval_width"] > 0
    assert by_method["seasonal_naive"]["interval_coverage"] is None
    engine.dispose()


def test_model_cannot_be_checked_on_its_own_training_history(tmp_path):
    from tram.application.errors import ApplicationError

    late = {**MODEL_DOC, "training_history_end": "2026-09-25T00:00:00+03:00"}
    runner, revision, engine = _demo_runner(tmp_path, _DoubledModel(), late)
    with pytest.raises(ApplicationError, match="trained on history"):
        runner.execute(revision, "demo-validations-day", ["2026-09-19T00:00:00+03:00"])
    engine.dispose()
