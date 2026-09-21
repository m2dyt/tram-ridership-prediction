import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from tram.application.metro import prepare_metro
from tram.cli import main
from tram.domain.metro import (
    MetroEntrance,
    MetroFlow,
    Quarter,
    QuarterlyPoint,
    QuarterSplit,
    quarter_grid,
    series_identity,
)
from tram.infrastructure.geo_import import read_geojson
from tram.infrastructure.metro_files import (
    read_entrances,
    read_flows,
    read_prepared,
    write_bundle,
)
from tram_ml.quarterly import evaluate_quarterly


@pytest.fixture(autouse=True)
def fixed_source_clock(monkeypatch):
    monkeypatch.setattr(
        "tram.infrastructure.metro_files.datetime",
        SimpleNamespace(now=lambda zone: datetime(2026, 9, 22, tzinfo=UTC)),
    )


def entrance(identity=1, station="Station", line="Line"):
    return MetroEntrance(identity, "Entrance", station, line, 37.6, 55.7, "действует", True)


def flow(identity, period, value=10, station="Station", line="Line"):
    return MetroFlow(identity, station, line, Quarter.parse(period), value, value + 1)


def source(tmp_path, dataset_id, rows):
    folder = tmp_path / dataset_id
    folder.mkdir()
    path = folder / "source.json"
    raw = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    path.write_bytes(raw)
    (folder / "provenance.json").write_text(
        json.dumps(
            {
                "provider": "data.mos.ru",
                "dataset_id": dataset_id,
                "source_url": f"https://data.mos.ru/opendata/{dataset_id}",
                "source_version": "1.0",
                "retrieved_at": "2026-09-21T00:00:00Z",
                "artifacts": [{"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()}],
            }
        ),
        encoding="utf-8",
    )
    return path


def geo_record():
    return {
        "global_id": 1,
        "Name": "Entrance",
        "NameOfStation": "Station",
        "Line": "Line",
        "Longitude_WGS84": "37.6",
        "Latitude_WGS84": "55.7",
        "geoData": [{"type": "Point", "coordinates": [37.6, 55.7]}],
        "ObjectStatus": "временно закрыт",
        "OnTerritoryOfMoscow": "нет",
    }


def flow_record():
    return {
        "global_id": 2,
        "NameOfStation": "Station",
        "Line": "Line",
        "Year": 2021,
        "Quarter": "I квартал",
        "IncomingPassengers": 0,
        "OutgoingPassengers": 0,
    }


def test_preparation_preserves_zeros_gaps_and_unresolved_identity():
    zero = replace(flow(1, "2021-Q1", 0), outgoing=0)
    flows = (zero, flow(2, "2021-Q3", 20), flow(3, "2021-Q2", station="Unknown"))
    prepared = prepare_metro((entrance(), entrance(2)), flows)
    counts = prepared["quality.json"]["issue_counts"]
    assert counts == {
        "missing_source_period": 1,
        "outside_source_span": 2,
        "unresolved_geo_match": 1,
        "zero_flow_unverified": 1,
    }
    points = prepared["quarters.jsonl"]
    station_id = series_identity("Station", "Line")
    target = next(p for p in points if p["series_id"] == station_id and p["quarter"] == "2021-Q2")
    assert target["incoming"] is None and target["missing_reason"] == "missing_source_period"
    assert next(p for p in points if p["source_record_id"] == 1)["incoming"] == 0
    # Two entrances must not double the observations or passenger values.
    assert len(points) == 6
    assert sum(p["incoming"] or 0 for p in points) == 30
    assert prepared == prepare_metro((entrance(2), entrance()), tuple(reversed(flows)))
    assert series_identity("Station", "Other line") != station_id


def test_duplicate_period_and_duplicate_id_are_not_silently_aggregated():
    with pytest.raises(ValueError, match="Duplicate station"):
        prepare_metro((entrance(),), (flow(1, "2021-Q1"), flow(2, "2021-Q1")))
    with pytest.raises(ValueError, match="Duplicate source"):
        prepare_metro((entrance(), entrance()), (flow(1, "2021-Q1"),))


def test_geojson_is_accepted_by_existing_importer_and_status_is_preserved(tmp_path):
    row = geo_record()
    path = source(tmp_path, "624", [row])
    entrances, _ = read_entrances(path)
    prepared = prepare_metro(entrances, (flow(2, "2021-Q1"),))
    geo = tmp_path / "entrances.geojson"
    geo.write_text(json.dumps(prepared["entrances.geojson"]), encoding="utf-8")
    result = read_geojson(geo, "https://data.mos.ru/opendata/624", "metro", "global_id", "Name")
    assert result["record_count"] == 1
    assert (
        prepared["entrances.geojson"]["features"][0]["properties"]["ObjectStatus"]
        == "временно закрыт"
    )
    assert prepared["quality.json"]["outside_moscow_entrances"] == 1


@pytest.mark.parametrize(
    "field,value",
    [("IncomingPassengers", -1), ("OutgoingPassengers", True), ("Year", 2021.0), ("Quarter", "Q1")],
)
def test_source_rejects_invalid_counts_and_quarters(tmp_path, field, value):
    row = flow_record() | {field: value}
    with pytest.raises(ValueError):
        read_flows(source(tmp_path, "62743", [row]))


def test_source_hash_and_coordinate_consistency_are_verified(tmp_path):
    path = source(tmp_path, "624", [geo_record()])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SHA-256"):
        read_entrances(path)
    bad = geo_record() | {"geoData": [{"type": "Point", "coordinates": [37.7, 55.7]}]}
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="disagree"):
        read_entrances(source(other, "624", [bad]))


def test_incomplete_future_quarter_is_rejected(tmp_path):
    row = flow_record() | {"Year": 2026, "Quarter": "III квартал"}
    with pytest.raises(ValueError, match="unfinished quarter"):
        read_flows(source(tmp_path, "62743", [row]))


def baseline_fixture():
    split = QuarterSplit(*(Quarter.parse(q) for q in ["2021-Q1", "2023-Q1", "2024-Q1", "2025-Q1"]))
    points = tuple(
        QuarterlyPoint("series", q, n, n + 1)
        for n, q in enumerate(quarter_grid(split.train_start, split.test_end))
    )
    return split, points


def test_baseline_reference_uses_only_completed_previous_year():
    split, points = baseline_fixture()
    result = evaluate_quarterly(points, split, "incoming")
    predictions = result["predictions.jsonl"]
    assert len(predictions) == 8
    assert [(r["actual"], r["prediction"]) for r in predictions] == [
        (n, n - 4) for n in range(8, 16)
    ]
    changed = tuple(
        replace(p, incoming=999999) if p.quarter >= split.test_start else p for p in points
    )
    new = evaluate_quarterly(changed, split, "incoming")["predictions.jsonl"]
    assert [r["prediction"] for r in new] == [r["prediction"] for r in predictions]
    assert set(r["partition"] for r in result["membership.jsonl"]) == {
        "train",
        "validation",
        "test",
    }
    assert not result["splits.json"]["fit_executed"]


def test_missing_reference_and_missing_actual_reduce_coverage_explicitly():
    split, points = baseline_fixture()
    points = tuple(
        replace(p, incoming=None, outgoing=None, missing_reason="missing_source_period")
        if str(p.quarter) in ("2022-Q1", "2023-Q2")
        else p
        for p in points
    )
    result = evaluate_quarterly(points, split, "incoming")
    validation = next(
        r
        for r in result["scores.json"]
        if r["partition"] == "validation" and r["series_id"] is None
    )
    assert validation["observed_points"] == 3 and validation["sample_count"] == 2
    assert validation["excluded_count"] == 2
    assert validation["coverage_on_observed"] == pytest.approx(2 / 3)
    assert result["predictions.jsonl"][0]["prediction"] is None


def test_zero_targets_have_zero_mae_and_undefined_wape():
    split, points = baseline_fixture()
    result = evaluate_quarterly(tuple(replace(p, incoming=0) for p in points), split, "incoming")
    scores = result["scores.json"][0]
    assert scores["mae"] == 0 and scores["wape"] is None
    assert scores["wape_unavailable_reason"] == "zero_actual_sum"


def test_rolling_test_uses_a_past_test_quarter_only_a_year_later():
    split, points = baseline_fixture()
    split = replace(split, test_end=Quarter(2026, 1))
    points += tuple(
        QuarterlyPoint("series", q, 20, 21) for q in quarter_grid(Quarter(2025, 1), split.test_end)
    )
    altered = tuple(
        replace(p, incoming=900) if p.quarter == Quarter(2024, 1) else p for p in points
    )
    base = evaluate_quarterly(points, split, "incoming")["predictions.jsonl"]
    new = evaluate_quarterly(altered, split, "incoming")["predictions.jsonl"]
    changed = [
        (a["quarter"], b["prediction"])
        for a, b in zip(base, new, strict=True)
        if a["prediction"] != b["prediction"]
    ]
    assert changed == [("2025-Q1", 900)]


def test_series_named_all_does_not_collide_with_aggregate_group():
    split, points = baseline_fixture()
    result = evaluate_quarterly(
        tuple(replace(p, series_id="all") for p in points), split, "incoming"
    )
    totals = [r for r in result["scores.json"] if r["series_id"] is None]
    assert len(totals) == 2 and all(r["sample_count"] == 4 for r in totals)


def test_split_and_grid_reject_truncation_duplicates_and_disorder():
    split, points = baseline_fixture()
    for invalid in (points[:-1], points + (points[0],), points[:2] + points[3:]):
        with pytest.raises(ValueError):
            evaluate_quarterly(invalid, split, "incoming")
    with pytest.raises(ValueError, match="ordered"):
        replace(split, validation_start=split.test_start)


def test_bundle_integrity_and_existing_output_are_protected(tmp_path):
    docs = prepare_metro((entrance(),), (flow(1, "2021-Q1"),))
    metadata = {"kind": "metro_research_bundle_v1", "revision": "test-v1"}
    out = tmp_path / "prepared"
    write_bundle(out, docs, metadata)
    manifest, points, _ = read_prepared(out)
    assert manifest["revision"] == "test-v1" and len(points) == 1
    with pytest.raises(FileExistsError):
        write_bundle(out, docs, metadata)
    (out / "quarters.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        read_prepared(out)


def test_cli_preparation_and_evaluation_need_no_env_or_database(tmp_path, monkeypatch):
    import tram.infrastructure.database
    import tram.infrastructure.settings

    def forbidden(*args, **kwargs):
        pytest.fail("Offline command accessed settings or database")

    monkeypatch.setattr(tram.infrastructure.settings, "Settings", forbidden)
    monkeypatch.setattr(tram.infrastructure.database, "make_engine", forbidden)
    geo = source(tmp_path, "624", [geo_record()])
    rows = []
    for index, q in enumerate(quarter_grid(Quarter(2021, 1), Quarter(2025, 1))):
        rows.append(
            flow_record()
            | {
                "global_id": index + 1,
                "Year": q.year,
                "Quarter": ["I", "II", "III", "IV"][q.number - 1] + " квартал",
            }
        )
    observations = source(tmp_path, "62743", rows)
    output = tmp_path / "prepared"
    assert (
        main(
            ["prepare-metro", str(geo), str(observations), str(output), "--revision", "fixture-v1"]
        )
        == 0
    )
    evaluation = tmp_path / "evaluation"
    assert (
        main(
            [
                "evaluate-metro",
                str(output),
                str(evaluation),
                "--revision",
                "eval-v1",
                "--train-start",
                "2021-Q1",
                "--validation-start",
                "2023-Q1",
                "--test-start",
                "2024-Q1",
                "--test-end",
                "2025-Q1",
            ]
        )
        == 0
    )
    assert (
        json.loads((evaluation / "manifest.json").read_text(encoding="utf-8"))["training_performed"]
        is False
    )
