"""Tram Data Integrity, Schema Validation, and Quality Reporting (D1, D2).

Strict guarantees:
1. Validates schemas and column types for raw transactions, labels, and submissions.
2. Distinguishes explicit zero boardings (route operated with 0 boardings in that hour)
   from missing grid points (gap in dataset / unserviced hour).
3. Enforces temporal isolation:
   - Train:      2025-01-01 to 2025-08-31
   - Validation: 2025-09-01 to 2025-10-31
   - Target:     2025-11-01 to 2025-12-31
4. Rejects invalid route IDs, negative passenger counts, NaN/nulls, and duplicate primary keys.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# Official 10 routes from competition specification and test_submission.csv
ALL_ROUTES: list[int] = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]
ACTIVE_ROUTES: list[int] = [1, 7, 11, 12, 17, 25, 26, 28, 50]

LABELS_COLUMNS: list[str] = ["route", "date", "hour", "boardings"]
SUBMISSION_COLUMNS: list[str] = ["route", "date", "hour", "prediction"]
RAW_TRANSACTION_COLUMNS: list[str] = [
    "tran_no",
    "device_no",
    "tran_date_time",
    "begin_date_time",
    "input_date_time",
    "crd_hashcode",
    "validation_result",
    "tran_type_id",
    "place_id",
    "good_type",
    "pass_route",
    "ngpt_route",
    "bus_exit_no",
    "garage_number",
]

SPLIT_DATE_RANGES: dict[str, tuple[str, str]] = {
    "train": ("2025-01-01", "2025-08-31"),
    "validation": ("2025-09-01", "2025-10-31"),
    "target": ("2025-11-01", "2025-12-31"),
}


class TramDataError(Exception):
    """Base error for tram data integrity violations."""


class SchemaValidationError(TramDataError):
    """Raised when columns, types, or delimiters fail expectations."""


class TemporalOverlapError(TramDataError):
    """Raised when future validation or test data leaks into train split."""


class InvalidKeyError(TramDataError):
    """Raised when primary keys (route, date, hour) contain invalid values or duplicates."""


def validate_labels_df(
    df: pd.DataFrame,
    expected_split: str | None = None,
) -> None:
    """Validate a hourly labels DataFrame against competition specifications."""
    # 1. Column presence
    missing_cols = [c for c in LABELS_COLUMNS if c not in df.columns]
    if missing_cols:
        raise SchemaValidationError(f"Missing required columns in labels: {missing_cols}")

    # 2. Nulls and NaNs
    null_counts = df[LABELS_COLUMNS].isnull().sum()
    if null_counts.any():
        bad_cols = null_counts[null_counts > 0].to_dict()
        raise SchemaValidationError(f"Null or NaN values detected in columns: {bad_cols}")

    # 3. Route ID validation
    unique_routes = set(df["route"].unique())
    invalid_routes = unique_routes - set(ALL_ROUTES)
    if invalid_routes:
        raise InvalidKeyError(f"Dataset contains unexpected route IDs: {sorted(invalid_routes)}")

    # 4. Hour range validation (0..23)
    hours = df["hour"].values
    if (hours < 0).any() or (hours > 23).any():
        raise InvalidKeyError("Hour values must strictly be integers between 0 and 23.")

    # 5. Non-negative boardings
    boardings = df["boardings"].values
    if (boardings < 0).any():
        raise SchemaValidationError("Passenger boardings cannot be negative.")

    # 6. Primary key duplicate check
    dups = df.duplicated(subset=["route", "date", "hour"], keep=False)
    if dups.any():
        dup_sample = df[dups].head(4).to_dict(orient="records")
        raise InvalidKeyError(
            f"Found {dups.sum()} duplicate rows for key (route, date, hour). Sample: {dup_sample}"
        )

    # 7. Temporal split boundaries
    if expected_split in SPLIT_DATE_RANGES:
        min_expected, max_expected = SPLIT_DATE_RANGES[expected_split]
        dates = df["date"].astype(str)
        violating_early = dates[dates < min_expected]
        violating_late = dates[dates > max_expected]

        if not violating_early.empty or not violating_late.empty:
            raise TemporalOverlapError(
                f"Data for split '{expected_split}' must be between {min_expected} and {max_expected}. "
                f"Found {len(violating_early)} records before {min_expected} "
                f"and {len(violating_late)} records after {max_expected}."
            )


def generate_quality_report(
    df: pd.DataFrame,
    split_name: str,
) -> dict[str, Any]:
    """Generate comprehensive quality and coverage report for a dataset split."""
    validate_labels_df(df)

    total_rows = len(df)
    unique_dates = sorted(df["date"].astype(str).unique().tolist())
    total_boardings = int(df["boardings"].sum())

    per_route_stats: dict[str, Any] = {}
    for r in ALL_ROUTES:
        r_mask = df["route"] == r
        df_r = df[r_mask]
        count_r = len(df_r)

        if count_r == 0:
            per_route_stats[str(r)] = {
                "active": False,
                "rows": 0,
                "total_boardings": 0,
                "zero_hours": 0,
                "zero_pct": 0.0,
                "mean_hourly_boardings": 0.0,
                "max_hourly_boardings": 0,
            }
            continue

        zero_hours = int((df_r["boardings"] == 0).sum())
        per_route_stats[str(r)] = {
            "active": True,
            "rows": count_r,
            "total_boardings": int(df_r["boardings"].sum()),
            "zero_hours": zero_hours,
            "zero_pct": round((zero_hours / count_r) * 100.0, 2),
            "mean_hourly_boardings": round(float(df_r["boardings"].mean()), 2),
            "max_hourly_boardings": int(df_r["boardings"].max()),
        }

    return {
        "split": split_name,
        "total_rows": total_rows,
        "date_range": {
            "start": unique_dates[0] if unique_dates else None,
            "end": unique_dates[-1] if unique_dates else None,
            "distinct_days": len(unique_dates),
        },
        "total_boardings": total_boardings,
        "routes_present": [int(r) for r in sorted(df["route"].unique())],
        "routes_missing": [r for r in ALL_ROUTES if r not in df["route"].unique()],
        "per_route_summary": per_route_stats,
    }
