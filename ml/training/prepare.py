"""Prepare feature matrices from a prepared metro research bundle.

Extracts seasonal lags, rolling averages, calendar factors, and spatial features
strictly without data leakage (using only information available before the target period).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend" / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend" / "src"))
if str(ROOT / "ml" / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "ml" / "src"))

from tram.domain.metro import Quarter


def parse_bundle(bundle_dir: Path) -> tuple[dict, list[dict], list[dict], dict[str, int]]:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found in {bundle_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("kind") != "metro_research_bundle_v1":
        raise ValueError(f"Expected kind 'metro_research_bundle_v1', got '{manifest.get('kind')}'")

    series_list = json.loads((bundle_dir / "series.json").read_text(encoding="utf-8"))
    quarters_lines = (bundle_dir / "quarters.jsonl").read_text(encoding="utf-8").splitlines()
    quarters_records = [json.loads(line) for line in quarters_lines if line.strip()]

    # Parse entrance counts per station from entrances.geojson
    entrances_count: dict[str, int] = {}
    geojson_path = bundle_dir / "entrances.geojson"
    if geojson_path.is_file():
        geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
        for feature in geojson.get("features", []):
            station = feature.get("properties", {}).get("NameOfStation")
            if station:
                entrances_count[station] = entrances_count.get(station, 0) + 1

    return manifest, series_list, quarters_records, entrances_count


def extract_features(
    series_list: list[dict],
    quarters_records: list[dict],
    entrances_count: dict[str, int],
    metric: str = "incoming",
) -> list[dict]:
    # Index series metadata
    series_meta = {s["series_id"]: s for s in series_list}

    # Group points by series_id
    by_series: dict[str, list[dict]] = {}
    for r in quarters_records:
        sid = r["series_id"]
        by_series.setdefault(sid, []).append(r)

    rows: list[dict] = []

    for sid, points in by_series.items():
        meta = series_meta.get(sid, {})
        station_name = meta.get("station_name", "Unknown")
        line = meta.get("line", "Unknown")
        num_entrances = entrances_count.get(station_name, 1)

        # Sort points by quarter
        sorted_points = sorted(points, key=lambda p: Quarter.parse(p["quarter"]))

        # Build chronological history
        history: dict[Quarter, float | None] = {}
        for p in sorted_points:
            q = Quarter.parse(p["quarter"])
            val = p.get(metric)
            history[q] = float(val) if val is not None else None

        for p in sorted_points:
            q = Quarter.parse(p["quarter"])
            target = p.get(metric)
            target_val = float(target) if target is not None else None

            # Historical lags (completed periods before q)
            lag_1 = history.get(q.shift(-1))
            lag_2 = history.get(q.shift(-2))
            lag_3 = history.get(q.shift(-3))
            lag_4 = history.get(q.shift(-4))  # same quarter previous year
            lag_5 = history.get(q.shift(-5))

            # Rolling statistics from valid lags
            past_lags = [x for x in (lag_1, lag_2, lag_3, lag_4) if x is not None]
            rolling_mean_4 = sum(past_lags) / len(past_lags) if len(past_lags) >= 2 else None

            # Year-over-year momentum
            trend_ratio_yoy = (
                (lag_1 - lag_5) / lag_5
                if (lag_1 is not None and lag_5 is not None and lag_5 > 0)
                else 0.0
            )

            row = {
                "series_id": sid,
                "station_name": station_name,
                "line": line,
                "quarter": str(q),
                "year": q.year,
                "quarter_num": q.number,
                "entrances_count": num_entrances,
                "lag_1": lag_1,
                "lag_2": lag_2,
                "lag_3": lag_3,
                "lag_4": lag_4,
                "lag_5": lag_5,
                "rolling_mean_4": rolling_mean_4,
                "trend_ratio_yoy": trend_ratio_yoy,
                "target": target_val,
                "is_observed": target_val is not None,
                "missing_reason": p.get("missing_reason"),
            }
            rows.append(row)

    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare features from a metro research bundle")
    parser.add_argument(
        "--bundle",
        type=Path,
        default=Path("data/metro/moscow-20260922"),
        help="Path to prepared metro research bundle",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/training/metro-v1"),
        help="Path to output feature directory",
    )
    parser.add_argument(
        "--metric",
        choices=["incoming", "outgoing"],
        default="incoming",
        help="Target metric to extract features for",
    )

    args = parser.parse_args(argv)
    bundle_dir: Path = args.bundle.resolve()
    output_dir: Path = args.output.resolve()

    if not bundle_dir.is_dir():
        print(f"Error: bundle directory not found: {bundle_dir}", file=sys.stderr)
        return 1

    try:
        manifest, series_list, quarters_records, entrances_count = parse_bundle(bundle_dir)
    except Exception as e:
        print(f"Error parsing bundle: {e}", file=sys.stderr)
        return 1

    feature_rows = extract_features(series_list, quarters_records, entrances_count, metric=args.metric)

    output_dir.mkdir(parents=True, exist_ok=True)
    features_file = output_dir / "features.jsonl"

    features_raw = b"".join(
        (json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        for r in feature_rows
    )
    features_file.write_bytes(features_raw)
    features_sha = hashlib.sha256(features_raw).hexdigest()

    metadata = {
        "kind": "training_features_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "source_bundle": str(bundle_dir.relative_to(ROOT) if ROOT in bundle_dir.parents else bundle_dir),
        "source_bundle_revision": manifest.get("revision"),
        "metric": args.metric,
        "feature_count": len(feature_rows),
        "features_file": "features.jsonl",
        "features_sha256": features_sha,
        "feature_columns": [
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
        ],
        "categorical_columns": ["line"],
    }

    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "status": "success",
                "output_dir": str(output_dir),
                "metric": args.metric,
                "rows": len(feature_rows),
                "features_sha256": features_sha[:16],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
