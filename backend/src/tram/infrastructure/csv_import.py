"""Streaming interchange for already aggregated, timestamped source data."""

import csv
import json

from tram.domain.series import nonnegative
from tram.infrastructure.contract import strict_json

COLUMNS = [
    "profile_id",
    "level",
    "route_id",
    "direction_id",
    "stop_id",
    "stop_sequence",
    "segment_id",
    "interval_start",
    "interval_end",
    "available_at",
    "value",
    "value_kind",
    "estimation_method",
    "missing_reason",
]


def prepare_csv(manifest_path, csv_path, directory, contract):
    # Output is exclusive. An interrupted conversion never publishes any database state.
    directory.mkdir(parents=True, exist_ok=False)
    manifest = strict_json(manifest_path.read_bytes())
    count = 0
    with (
        csv_path.open(encoding="utf-8-sig", newline="") as source,
        (directory / "observations.jsonl").open("x", encoding="utf-8", newline="\n") as target,
    ):
        reader = csv.DictReader(source)
        if reader.fieldnames != COLUMNS:
            raise ValueError(
                "CSV columns must exactly match the documented aggregate interchange header"
            )
        for row in reader:
            value = float(row["value"]) if row["value"] else None
            if value is not None:
                nonnegative(value)
            spatial = {k: row[k] or None for k in COLUMNS[1:7]}
            spatial["stop_sequence"] = int(row["stop_sequence"]) if row["stop_sequence"] else None
            point = {
                "spatial": spatial,
                "interval_start": row["interval_start"],
                "interval_end": row["interval_end"],
                "value": value,
                "value_kind": row["value_kind"],
                "estimation_method": row["estimation_method"] or None,
                "missing_reason": row["missing_reason"] or None,
                "quality": {
                    "status": "missing" if value is None else "unverified",
                    "coverage_ratio": None,
                    "flags": ["csv_import"],
                },
            }
            contract.validate("ObservationPoint", point)
            contract.validator({"type": "string", "format": "date-time"}).validate(
                row["available_at"]
            )
            target.write(
                json.dumps(
                    {
                        "profile_id": row["profile_id"],
                        "available_at": row["available_at"],
                        "point": point,
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            )
            count += 1
    # The manifest acts as the completion marker; semantic checks run atomically at publish.
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return count
