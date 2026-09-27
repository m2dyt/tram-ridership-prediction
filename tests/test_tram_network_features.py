"""Tests for tram network spatial and operational features extracted from moscow-public-transport."""

import json
from pathlib import Path

import pandas as pd

from ml.training.tram.features import (
    ALL_ROUTES,
    ROUTE_STATIC_FEATURE_COLS,
    attach_route_features,
)


def test_tram_route_features_table_integrity():
    features_path = Path("data/tram_route_features.csv")
    assert features_path.is_file(), f"Missing {features_path}"

    df = pd.read_csv(features_path)
    assert len(df) == 10
    assert set(df["route"].tolist()) == set(ALL_ROUTES)

    # Route 5 must be inactive and zeroed
    r5 = df[df["route"] == 5].iloc[0]
    assert r5["route_is_active"] == 0
    assert r5["route_num_stops"] == 0
    assert r5["route_length_km"] == 0.0
    assert r5["route_segregated_ratio"] == 0.0
    assert r5["route_shared_stops"] == 0

    # Active routes must have valid positive values
    for r_num in [1, 7, 11, 12, 17, 25, 26, 28, 50]:
        row = df[df["route"] == r_num].iloc[0]
        assert row["route_is_active"] == 1
        assert row["route_num_stops"] > 10
        assert row["route_length_km"] > 5.0
        assert 0.0 <= row["route_late_ratio"] <= 100.0
        assert 0.0 <= row["route_punctuality_ratio"] <= 100.0
        assert row["route_fleet_proxy"] > 0
        assert 0.0 <= row["route_segregated_ratio"] <= 1.0

    # Specific track segregation tests
    r17 = df[df["route"] == 17].iloc[0]
    assert r17["route_segregated_ratio"] == 1.0
    assert r17["route_shared_stops"] == 0

    r50 = df[df["route"] == 50].iloc[0]
    assert 0.4 <= r50["route_segregated_ratio"] <= 0.6
    assert r50["route_shared_stops"] > 30


def test_attach_route_features():
    df_grid = pd.DataFrame(
        {
            "route": [1, 5, 17],
            "date": ["2025-05-01", "2025-05-01", "2025-05-01"],
            "hour": [10, 10, 10],
        }
    )

    df_attached = attach_route_features(df_grid)
    assert len(df_attached) == 3

    for col in ROUTE_STATIC_FEATURE_COLS:
        assert col in df_attached.columns
        assert not df_attached[col].isna().any()

    # Verify Route 17 values
    r17 = df_attached[df_attached["route"] == 17].iloc[0]
    assert r17["route_num_stops"] == 52
    assert r17["route_is_active"] == 1

    # Verify Route 5 values
    r5 = df_attached[df_attached["route"] == 5].iloc[0]
    assert r5["route_is_active"] == 0
    assert r5["route_num_stops"] == 0


def test_tram_network_geojson_validity():
    geojson_path = Path("data/tram_network.geojson")
    assert geojson_path.is_file(), f"Missing {geojson_path}"

    with open(geojson_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert len(data["features"]) > 500

    # Check that both LineString and Point features exist
    geom_types = {feat["geometry"]["type"] for feat in data["features"]}
    assert "LineString" in geom_types
    assert "Point" in geom_types
