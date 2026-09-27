import pytest

from ml.training.prepare import extract_features
from ml.training.train import build_and_train_ridge, compute_metrics


def test_metrics_calculation():
    actuals = [100.0, 200.0, 300.0]
    preds = [110.0, 190.0, 300.0]
    metrics = compute_metrics(actuals, preds)
    assert metrics["mae"] == pytest.approx(6.67, rel=1e-2)
    assert metrics["wape"] == pytest.approx(20.0 / 600.0, rel=1e-3)
    assert metrics["count"] == 3


def test_metrics_empty():
    metrics = compute_metrics([], [])
    assert metrics["mae"] == 0.0
    assert metrics["wape"] is None
    assert metrics["count"] == 0


def test_feature_extraction_has_no_future_leakage():
    series_list = [{"series_id": "s1", "station_name": "TestStation", "line": "Line 1"}]
    quarters_records = [
        {
            "series_id": "s1",
            "quarter": "2021-Q1",
            "incoming": 100,
            "outgoing": 100,
            "missing_reason": None,
        },
        {
            "series_id": "s1",
            "quarter": "2021-Q2",
            "incoming": 110,
            "outgoing": 110,
            "missing_reason": None,
        },
        {
            "series_id": "s1",
            "quarter": "2021-Q3",
            "incoming": 120,
            "outgoing": 120,
            "missing_reason": None,
        },
        {
            "series_id": "s1",
            "quarter": "2021-Q4",
            "incoming": 130,
            "outgoing": 130,
            "missing_reason": None,
        },
        {
            "series_id": "s1",
            "quarter": "2022-Q1",
            "incoming": 140,
            "outgoing": 140,
            "missing_reason": None,
        },
    ]
    entrances = {"TestStation": 3}

    features = extract_features(series_list, quarters_records, entrances, metric="incoming")
    assert len(features) == 5

    # 2021-Q1 has no past lags
    q1 = features[0]
    assert q1["quarter"] == "2021-Q1"
    assert q1["quarter_num"] == 1
    assert q1["lag_1"] is None
    assert q1["lag_4"] is None
    assert q1["target"] == 100.0
    assert q1["entrances_count"] == 3

    # 2022-Q1 has lag_1=130 (2021-Q4) and lag_4=100 (2021-Q1)
    q5 = features[4]
    assert q5["quarter"] == "2022-Q1"
    assert q5["lag_1"] == 130.0
    assert q5["lag_4"] == 100.0
    assert q5["target"] == 140.0

    # Changing future value does not affect past feature rows
    changed_records = list(quarters_records)
    changed_records[4] = dict(changed_records[4], incoming=999999)
    changed_features = extract_features(series_list, changed_records, entrances, metric="incoming")

    for i in range(4):
        assert features[i] == changed_features[i]


def test_ridge_pipeline_training_and_validation():
    pytest.importorskip("sklearn")
    pytest.importorskip("pandas")

    train_rows = [
        {
            "series_id": f"s{i}",
            "station_name": f"St{i}",
            "line": "L1" if i % 2 == 0 else "L2",
            "quarter": "2021-Q1",
            "quarter_num": 1,
            "year": 2021,
            "entrances_count": 2,
            "lag_1": 100.0 + i,
            "lag_2": 95.0 + i,
            "lag_3": 90.0 + i,
            "lag_4": 85.0 + i,
            "lag_5": 80.0 + i,
            "rolling_mean_4": 92.5 + i,
            "trend_ratio_yoy": 0.1,
            "target": 105.0 + i,
            "is_observed": True,
        }
        for i in range(20)
    ]
    val_rows = [
        {
            "series_id": f"s{i}",
            "station_name": f"St{i}",
            "line": "L1" if i % 2 == 0 else "L2",
            "quarter": "2022-Q1",
            "quarter_num": 1,
            "year": 2022,
            "entrances_count": 2,
            "lag_1": 105.0 + i,
            "lag_2": 100.0 + i,
            "lag_3": 95.0 + i,
            "lag_4": 90.0 + i,
            "lag_5": 85.0 + i,
            "rolling_mean_4": 97.5 + i,
            "trend_ratio_yoy": 0.1,
            "target": 110.0 + i,
            "is_observed": True,
        }
        for i in range(10)
    ]

    feature_cols = [
        "quarter_num",
        "year",
        "entrances_count",
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_4",
        "lag_5",
        "rolling_mean_4",
        "trend_ratio_yoy",
    ]
    cat_cols = ["line"]

    model, metrics = build_and_train_ridge(
        train_rows, val_rows, feature_cols, cat_cols, {"alpha": 1.0}, seed=42
    )
    assert model is not None
    assert metrics["mae"] >= 0
    assert metrics["wape"] is not None
    assert metrics["count"] == len(val_rows)


def test_line_name_mapping_in_extract_features():
    """Verify line_name is properly mapped to line in extracted features."""
    series_list = [
        {"series_id": "s1", "station_name": "Station A", "line_name": "Sokolnicheskaya Line"}
    ]
    quarters_records = [
        {
            "series_id": "s1",
            "quarter": "2021-Q1",
            "incoming": 100,
            "outgoing": 100,
            "missing_reason": None,
        }
    ]
    features = extract_features(series_list, quarters_records, {}, metric="incoming")
    assert len(features) == 1
    assert features[0]["line"] == "Sokolnicheskaya Line"


def test_hist_gbdt_training_with_categories():
    """Verify HistGradientBoosting training with categorical line column works cleanly."""
    pytest.importorskip("sklearn")
    pytest.importorskip("pandas")
    from ml.training.train import build_and_train_hist_gbdt

    train_rows = [
        {
            "series_id": f"s{i}",
            "station_name": f"St{i}",
            "line": "Red" if i % 2 == 0 else "Blue",
            "quarter": "2021-Q1",
            "quarter_num": 1,
            "year": 2021,
            "entrances_count": 2,
            "lag_1": 100.0 + i,
            "lag_2": 95.0 + i,
            "lag_3": 90.0 + i,
            "lag_4": 85.0 + i,
            "lag_5": 80.0 + i,
            "rolling_mean_4": 92.5 + i,
            "trend_ratio_yoy": 0.05,
            "target": 105.0 + i,
            "is_observed": True,
        }
        for i in range(20)
    ]
    val_rows = [
        {
            "series_id": f"s{i}",
            "station_name": f"St{i}",
            "line": "Red" if i % 2 == 0 else "Blue",
            "quarter": "2022-Q1",
            "quarter_num": 1,
            "year": 2022,
            "entrances_count": 2,
            "lag_1": 105.0 + i,
            "lag_2": 100.0 + i,
            "lag_3": 95.0 + i,
            "lag_4": 90.0 + i,
            "lag_5": 85.0 + i,
            "rolling_mean_4": 97.5 + i,
            "trend_ratio_yoy": 0.1,
            "target": 110.0 + i,
            "is_observed": True,
        }
        for i in range(10)
    ]
    feature_cols = [
        "quarter_num",
        "year",
        "entrances_count",
        "lag_1",
        "lag_2",
        "lag_3",
        "lag_4",
        "lag_5",
        "rolling_mean_4",
        "trend_ratio_yoy",
    ]
    cat_cols = ["line"]

    model, metrics = build_and_train_hist_gbdt(
        train_rows, val_rows, feature_cols, cat_cols, {"max_iter": 10, "max_leaf_nodes": 7}, seed=42
    )
    assert model is not None
    assert metrics["mae"] >= 0
    assert metrics["wape"] is not None


def test_train_cli_overwrite_protection(tmp_path):
    """Verify train CLI prevents accidental overwrites unless --force is given."""
    pytest.importorskip("sklearn")
    pytest.importorskip("pandas")
    import json

    from ml.training.train import main as train_main

    # Create dummy features
    feat_dir = tmp_path / "features"
    feat_dir.mkdir()
    feat_file = feat_dir / "features.jsonl"
    rows = [
        {
            "series_id": f"s{i}",
            "station_name": f"St{i}",
            "line": "Red",
            "quarter": "2021-Q1" if i < 15 else "2024-Q1",
            "quarter_num": 1,
            "year": 2021 if i < 15 else 2024,
            "entrances_count": 2,
            "lag_1": 100.0,
            "lag_2": 95.0,
            "lag_3": 90.0,
            "lag_4": 85.0,
            "lag_5": 80.0,
            "rolling_mean_4": 92.5,
            "trend_ratio_yoy": 0.05,
            "target": 105.0,
            "is_observed": True,
        }
        for i in range(25)
    ]
    feat_file.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "model_type": "ridge",
                "train_start": "2021-Q1",
                "validation_start": "2024-Q1",
                "test_start": "2025-Q1",
                "test_end": "2026-Q3",
                "feature_columns": ["quarter_num", "year", "entrances_count", "lag_1"],
                "categorical_columns": ["line"],
            }
        ),
        encoding="utf-8",
    )

    model_dir = tmp_path / "model_out"

    # First run: should succeed
    ret1 = train_main(
        [
            "--features",
            str(feat_dir),
            "--config",
            str(config_path),
            "--output",
            str(model_dir),
        ]
    )
    assert ret1 == 0
    assert (model_dir / "model.joblib").is_file()
    assert (model_dir / "checksums.json").is_file()

    # Second run without --force: should fail with code 1
    ret2 = train_main(
        [
            "--features",
            str(feat_dir),
            "--config",
            str(config_path),
            "--output",
            str(model_dir),
        ]
    )
    assert ret2 == 1

    # Third run with --force: should succeed
    ret3 = train_main(
        [
            "--features",
            str(feat_dir),
            "--config",
            str(config_path),
            "--output",
            str(model_dir),
            "--force",
        ]
    )
    assert ret3 == 0
