"""Competition submission validator for Tram Ridership Prediction.

Verifies:
1. File format, delimiter (;) and exact columns (route;date;hour;prediction).
2. Exact row count (14,640 data rows).
3. Exact set of routes (1, 5, 7, 11, 12, 17, 25, 26, 28, 50).
4. Date coverage (2025-11-01 to 2025-12-31, 61 days) and hours (0..23).
5. Route 5 rule: all predictions for route 5 must be strictly 0.
6. Non-negativity, no NaNs, nulls, or infs.
7. Exact key alignment and order against official test_submission.csv sample.
8. Distribution summary & optional comparison with baseline submission.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["route", "date", "hour", "prediction"]
EXPECTED_ROUTES = {1, 5, 7, 11, 12, 17, 25, 26, 28, 50}
EXPECTED_ROWS = 14640  # 61 days * 24 hours * 10 routes
START_DATE = "2025-11-01"
END_DATE = "2025-12-31"


class ValidationError(Exception):
    pass


def validate_submission(
    file_path: Path,
    sample_path: Path | None = None,
    baseline_path: Path | None = None,
    sort_to: Path | None = None,
) -> dict:
    errors = []
    warnings = []
    stats = {}

    if not file_path.is_file():
        raise ValidationError(f"File not found: {file_path}")

    # 1. Delimiter check
    with open(file_path, encoding="utf-8") as f:
        first_line = f.readline().strip()
        if ";" not in first_line:
            errors.append(f"Header delimiter is not ';': '{first_line}'")
        cols = [c.strip() for c in first_line.split(";")]
        if cols != REQUIRED_COLUMNS:
            errors.append(f"Header columns mismatch: expected {REQUIRED_COLUMNS}, got {cols}")

    # 2. Load via pandas
    try:
        df = pd.read_csv(file_path, sep=";")
    except Exception as e:
        raise ValidationError(f"Failed to parse CSV: {e}") from e

    # Check rows count
    if len(df) != EXPECTED_ROWS:
        errors.append(f"Row count mismatch: expected {EXPECTED_ROWS}, got {len(df)}")

    # Check columns
    if list(df.columns) != REQUIRED_COLUMNS:
        errors.append(f"Data columns mismatch: expected {REQUIRED_COLUMNS}, got {list(df.columns)}")

    if errors:
        return {"success": False, "errors": errors, "warnings": warnings, "stats": stats}

    # 3. Check types & missing values
    for col in REQUIRED_COLUMNS:
        null_count = df[col].isna().sum()
        if null_count > 0:
            errors.append(f"Column '{col}' has {null_count} null/NaN values")

    # 4. Check routes
    routes_found = set(df["route"].unique())
    if routes_found != EXPECTED_ROUTES:
        diff_missing = EXPECTED_ROUTES - routes_found
        diff_unexpected = routes_found - EXPECTED_ROUTES
        if diff_missing:
            errors.append(f"Missing expected routes: {sorted(diff_missing)}")
        if diff_unexpected:
            errors.append(f"Unexpected routes found: {sorted(diff_unexpected)}")

    # 5. Check hours
    hours_found = set(df["hour"].unique())
    expected_hours = set(range(24))
    if hours_found != expected_hours:
        errors.append(f"Hours mismatch: expected 0..23, got {sorted(hours_found)}")

    # 6. Check dates
    dates_found = sorted(df["date"].unique())
    expected_date_range = [d.strftime("%Y-%m-%d") for d in pd.date_range(START_DATE, END_DATE)]
    if dates_found != expected_date_range:
        errors.append(
            f"Date range mismatch: expected {len(expected_date_range)} days ({START_DATE} to {END_DATE}), got {len(dates_found)} days"
        )

    # 7. Check key duplicates
    duplicates = df.duplicated(subset=["route", "date", "hour"]).sum()
    if duplicates > 0:
        errors.append(f"Found {duplicates} duplicate (route, date, hour) rows")

    # 8. Check Route 5 rule (all predictions must be exactly 0)
    route_5 = df[df["route"] == 5]
    if len(route_5) > 0:
        route_5_non_zero = (route_5["prediction"] != 0).sum()
        if route_5_non_zero > 0:
            errors.append(
                f"Route 5 rule violated: {route_5_non_zero} rows have non-zero predictions (must all be 0)"
            )

    # 9. Check non-negativity and finiteness
    negatives = (df["prediction"] < 0).sum()
    if negatives > 0:
        errors.append(f"Found {negatives} negative predictions")

    if not np.all(np.isfinite(df["prediction"].values)):
        errors.append("Predictions contain infinite values (inf or -inf)")

    # 10. Sample alignment check
    if sample_path and sample_path.is_file():
        sample_df = pd.read_csv(sample_path, sep=";")
        keys_match = (
            (df["route"] == sample_df["route"]).all()
            and (df["date"] == sample_df["date"]).all()
            and (df["hour"] == sample_df["hour"]).all()
        )
        if not keys_match:
            warnings.append(
                f"Row ordering does not match official sample '{sample_path.name}'. "
                "Keys exist, but row order is different."
            )
            if sort_to:
                # Merge with sample order to produce exact alignment
                aligned = sample_df[["route", "date", "hour"]].merge(
                    df, on=["route", "date", "hour"], how="left"
                )
                aligned.to_csv(sort_to, sep=";", index=False)
                warnings.append(f"Aligned submission saved to {sort_to}")
        else:
            stats["sample_exact_order_match"] = True

    # Compute statistics
    stats["total_predicted_passengers"] = int(df["prediction"].sum())
    stats["mean_prediction"] = float(df["prediction"].mean())
    stats["median_prediction"] = float(df["prediction"].median())
    stats["max_prediction"] = float(df["prediction"].max())
    stats["min_prediction"] = float(df["prediction"].min())

    per_route = {}
    for r in sorted(EXPECTED_ROUTES):
        r_df = df[df["route"] == r]
        per_route[str(r)] = {
            "sum": int(r_df["prediction"].sum()),
            "mean": round(float(r_df["prediction"].mean()), 2),
            "max": int(r_df["prediction"].max()),
        }
    stats["per_route"] = per_route

    # 11. Baseline comparison check if provided
    if baseline_path and baseline_path.is_file():
        base_df = pd.read_csv(baseline_path, sep=";")
        merged = df.merge(base_df, on=["route", "date", "hour"], suffixes=("_new", "_base"))
        if len(merged) == EXPECTED_ROWS:
            abs_diff = (merged["prediction_new"] - merged["prediction_base"]).abs()
            mae_vs_base = float(abs_diff.mean())
            wape_vs_base = (
                float(abs_diff.sum() / merged["prediction_base"].sum())
                if merged["prediction_base"].sum() > 0
                else 0.0
            )
            stats["comparison_vs_baseline"] = {
                "baseline_total_passengers": int(merged["prediction_base"].sum()),
                "total_difference": int(df["prediction"].sum() - merged["prediction_base"].sum()),
                "mae_vs_base": round(mae_vs_base, 2),
                "wape_discrepancy": round(wape_vs_base, 4),
            }

    success = len(errors) == 0
    return {"success": success, "errors": errors, "warnings": warnings, "stats": stats}


def main():
    parser = argparse.ArgumentParser(description="Validate competition submission file.")
    parser.add_argument("submission", type=Path, help="Path to submission.csv")
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path("dataset/test_submission.csv"),
        help="Path to official sample submission",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Path to baseline submission to compare against",
    )
    parser.add_argument(
        "--sort-to",
        type=Path,
        default=None,
        help="Optional path to output row-aligned submission according to sample order",
    )

    args = parser.parse_args()

    sample = args.sample if args.sample.is_file() else None
    result = validate_submission(
        args.submission,
        sample_path=sample,
        baseline_path=args.baseline,
        sort_to=args.sort_to,
    )

    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print(f"SUBMISSION VALIDATION REPORT: {args.submission.name}")
    print("=" * 60)

    if result["errors"]:
        print("\n[FAILED] VALIDATION FAILED WITH ERRORS:")
        for err in result["errors"]:
            print(f"  - [ERROR] {err}")
    else:
        print("\n[PASSED] ALL CRITICAL VALIDATION CHECKS PASSED!")

    if result["warnings"]:
        print("\n[WARNINGS]:")
        for warn in result["warnings"]:
            print(f"  - [WARN] {warn}")

    if result["stats"]:
        print("\n[SUMMARY] SUBMISSION STATS:")
        print(f"  Total predicted passengers : {result['stats']['total_predicted_passengers']:,}")
        print(f"  Mean passenger flow / hour : {result['stats']['mean_prediction']:.2f}")
        print(f"  Median flow / hour         : {result['stats']['median_prediction']:.1f}")
        print(f"  Max flow in single hour    : {result['stats']['max_prediction']}")
        print(f"  Min flow                   : {result['stats']['min_prediction']}")

        if "comparison_vs_baseline" in result["stats"]:
            comp = result["stats"]["comparison_vs_baseline"]
            print("\n[COMPARISON] WITH BASELINE:")
            print(f"  Baseline Total Passengers  : {comp['baseline_total_passengers']:,}")
            print(f"  Diff in Total Passengers   : {comp['total_difference']:+,}")
            print(f"  MAE discrepancy vs Base    : {comp['mae_vs_base']:.2f}")
            print(f"  WAPE divergence vs Base    : {comp['wape_discrepancy']:.2%}")

    print("=" * 60)
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
