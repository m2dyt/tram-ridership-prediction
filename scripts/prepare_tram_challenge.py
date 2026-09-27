"""CLI utility to unpack, audit, validate, and prepare competition datasets (D1, D2).

Actions:
1. Inspects raw dataset files (train.csv, test.csv, test_submission.csv, labels/).
2. Validates schema, key uniqueness, non-negativity, and temporal boundaries via tram_data.py.
3. Computes SHA-256 provenance hashes and writes sources/tram-competition-2025/provenance.json.
4. Generates immutable dataset manifest and quality reports in data/training/tram-competition-v1/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

# Ensure workspace root and ml/training are importable
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from ml.training.tram_data import (  # noqa: E402
    ALL_ROUTES,
    generate_quality_report,
    validate_labels_df,
)

OFFICIAL_SOURCE_ARCHIVE_URL = "https://disk.yandex.ru/d/DiFwlfMOauxjBg"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 checksum of a file in 64KB chunks."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def audit_and_prepare(
    dataset_dir: Path,
    sources_dir: Path,
    output_dir: Path,
    compute_heavy_hashes: bool = True,
) -> dict:
    """Audit dataset files and write provenance and manifest."""
    sources_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(" AUDITING TRAM COMPETITION DATASET (D1, D2)")
    print("=" * 72)
    print(f" Source Directory: {dataset_dir.resolve()}")
    print(f" Output Directory: {output_dir.resolve()}")
    print("-" * 72)

    files_audit: dict[str, dict] = {}
    known_files = [
        ("train.csv", "raw_train", True),
        ("test.csv", "raw_test", True),
        ("test_submission.csv", "sample_submission", False),
        ("labels/labels_day_train.csv", "labels_train", False),
        ("labels/labels_day_test.csv", "labels_validation", False),
    ]

    for rel_path, role, is_large in known_files:
        p = dataset_dir / rel_path
        if not p.is_file():
            print(f"  [MISSING] {rel_path}")
            continue

        size_bytes = p.stat().st_size
        size_mb = round(size_bytes / (1024 * 1024), 2)

        if is_large and not compute_heavy_hashes:
            file_hash = "skipped_large_file"
        else:
            print(f"  Calculating SHA-256 for {rel_path} ({size_mb} MB)...")
            file_hash = sha256_file(p)

        files_audit[rel_path] = {
            "role": role,
            "size_bytes": size_bytes,
            "size_mb": size_mb,
            "sha256": file_hash,
            "exists": True,
        }
        print(f"  [OK] {rel_path:<28} | {size_mb:>8.2f} MB | {file_hash[:16]}...")

    # Validate labels dataframes
    train_labels_p = dataset_dir / "labels" / "labels_day_train.csv"
    val_labels_p = dataset_dir / "labels" / "labels_day_test.csv"
    sub_sample_p = dataset_dir / "test_submission.csv"

    quality_reports: dict[str, dict] = {}

    if train_labels_p.is_file():
        print("  Validating labels_day_train.csv schema and constraints...")
        df_train = pd.read_csv(train_labels_p, sep=";")
        validate_labels_df(df_train, expected_split="train")
        train_rep = generate_quality_report(df_train, split_name="train")
        quality_reports["train"] = train_rep
        print(
            f"  [OK] Train labels valid: {train_rep['total_rows']} rows, {train_rep['total_boardings']} boardings"
        )

    if val_labels_p.is_file():
        print("  Validating labels_day_test.csv schema and constraints...")
        df_val = pd.read_csv(val_labels_p, sep=";")
        validate_labels_df(df_val, expected_split="validation")
        val_rep = generate_quality_report(df_val, split_name="validation")
        quality_reports["validation"] = val_rep
        print(
            f"  [OK] Validation labels valid: {val_rep['total_rows']} rows, {val_rep['total_boardings']} boardings"
        )

    if sub_sample_p.is_file():
        print("  Checking test_submission.csv sample format...")
        df_sub = pd.read_csv(sub_sample_p, sep=";")
        assert len(df_sub) == 14640, (
            f"Expected 14640 rows in test_submission.csv, found {len(df_sub)}"
        )
        assert list(df_sub.columns) == ["route", "date", "hour", "prediction"]
        print(f"  [OK] Submission sample valid: {len(df_sub)} rows covering 10 routes")

    # 1. Write provenance.json in sources/
    provenance = {
        "dataset_name": "МТТЕХ ИИ-прогноз загрузки трамвайных маршрутов",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source_archive_url": OFFICIAL_SOURCE_ARCHIVE_URL,
        "organizers": "МТТЕХ / Организаторы хакатона",
        "official_specification_doc": "ИИ-прогноз загрузки трамвайных маршрутов.pdf",
        "routes": ALL_ROUTES,
        "files": files_audit,
    }

    provenance_path = sources_dir / "provenance.json"
    with provenance_path.open("w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2, ensure_ascii=False)
    print(f"  [SAVED] Provenance passport -> {provenance_path}")

    # 2. Write manifest.json in data/training/tram-competition-v1/
    manifest = {
        "dataset_id": "tram-competition-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "splits": {
            "train": {
                "start": "2025-01-01",
                "end": "2025-08-31",
                "rows": quality_reports.get("train", {}).get("total_rows"),
                "total_boardings": quality_reports.get("train", {}).get("total_boardings"),
                "labels_file": "dataset/labels/labels_day_train.csv",
                "labels_sha256": files_audit.get("labels/labels_day_train.csv", {}).get("sha256"),
            },
            "validation": {
                "start": "2025-09-01",
                "end": "2025-10-31",
                "rows": quality_reports.get("validation", {}).get("total_rows"),
                "total_boardings": quality_reports.get("validation", {}).get("total_boardings"),
                "labels_file": "dataset/labels/labels_day_test.csv",
                "labels_sha256": files_audit.get("labels/labels_day_test.csv", {}).get("sha256"),
            },
            "target_submission": {
                "start": "2025-11-01",
                "end": "2025-12-31",
                "rows": 14640,
                "routes": 10,
                "hours_per_day": 24,
                "days": 61,
                "sample_file": "dataset/test_submission.csv",
                "sample_sha256": files_audit.get("test_submission.csv", {}).get("sha256"),
            },
        },
        "routes": ALL_ROUTES,
        "provenance_ref": str(provenance_path.as_posix()),
    }

    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  [SAVED] Dataset manifest -> {manifest_path}")

    # 3. Write quality_report.json
    quality_report_path = output_dir / "quality_report.json"
    with quality_report_path.open("w", encoding="utf-8") as f:
        json.dump(quality_reports, f, indent=2, ensure_ascii=False)
    print(f"  [SAVED] Quality report -> {quality_report_path}")

    print("=" * 72)
    print(" PREPARATION & AUDIT COMPLETE")
    print("=" * 72)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and audit tram competition datasets")
    parser.add_argument(
        "--dataset-dir", type=Path, default=Path("dataset"), help="Path to raw dataset directory"
    )
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=Path("sources/tram-competition-2025"),
        help="Path to sources dir",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/training/tram-competition-v1"),
        help="Manifest output dir",
    )
    parser.add_argument(
        "--quick", action="store_true", help="Skip SHA-256 for multi-gigabyte raw files"
    )
    args = parser.parse_args()

    audit_and_prepare(
        dataset_dir=args.dataset_dir,
        sources_dir=args.sources_dir,
        output_dir=args.output_dir,
        compute_heavy_hashes=not args.quick,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
