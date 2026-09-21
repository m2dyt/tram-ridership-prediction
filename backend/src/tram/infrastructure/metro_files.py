"""Strict file adapters for the downloaded 624/62743 snapshots and offline results."""

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path

from tram.domain.metro import MetroEntrance, MetroFlow, Quarter, QuarterlyPoint
from tram.domain.time import parse_time
from tram.infrastructure.contract import strict_json

MAX_BYTES = 50_000_000
PREPARED_FILES = {"entrances.geojson", "series.json", "quarters.jsonl", "quality.json"}


def read_bytes(path: Path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Metro file exceeds 50 MB")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("Metro file exceeds 50 MB")
    return raw


def text(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("Expected a nonempty source label without surrounding whitespace")
    return value


def integer(value, *, positive=False):
    if type(value) is not int or value < int(positive):
        raise ValueError("Expected a nonnegative integer, not a boolean or string")
    return value


def source_rows(path: Path, dataset_id: str):
    raw = read_bytes(path)
    digest = hashlib.sha256(raw).hexdigest()
    provenance = strict_json(read_bytes(path.parent / "provenance.json"))
    if (
        provenance["provider"] != "data.mos.ru"
        or provenance["dataset_id"] != dataset_id
        or provenance["source_url"] != f"https://data.mos.ru/opendata/{dataset_id}"
    ):
        raise ValueError("Source provenance does not identify the expected Moscow dataset")
    matching = [r for r in provenance["artifacts"] if r["file"] == path.name]
    if len(matching) != 1 or matching[0]["sha256"] != digest:
        raise ValueError("Source SHA-256 differs from provenance")
    retrieved = parse_time(provenance["retrieved_at"])
    if retrieved > datetime.now(UTC):
        raise ValueError("Source retrieval is in the future")
    rows = strict_json(raw)
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
        raise ValueError("Expected a nonempty JSON array of source records")
    return rows, {
        "dataset_id": dataset_id,
        "source_url": provenance["source_url"],
        "source_version": text(provenance["source_version"]),
        "raw_file": path.name,
        "sha256": digest,
        "retrieved_at": retrieved.isoformat(),
        "historical_availability_verified": False,
    }


def read_entrances(path: Path):
    rows, metadata = source_rows(path, "624")
    result = []
    for row in rows:
        values = row["Longitude_WGS84"], row["Latitude_WGS84"]
        if any(type(v) not in (str, float, int) for v in values):
            raise ValueError("Invalid coordinate type")
        lon, lat = map(float, values)
        if not (
            math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90
        ):
            raise ValueError("Invalid WGS84 coordinates")
        geometry = row["geoData"]
        if not isinstance(geometry, list) or len(geometry) != 1 or geometry[0]["type"] != "Point":
            raise ValueError("Expected a single geoData Point")
        coords = geometry[0]["coordinates"]
        if (
            not isinstance(coords, list)
            or len(coords) != 2
            or any(type(c) not in (int, float) or not math.isfinite(c) for c in coords)
            or abs(coords[0] - lon) > 1e-7
            or abs(coords[1] - lat) > 1e-7
        ):
            raise ValueError("geoData and WGS84 columns disagree")
        if row["OnTerritoryOfMoscow"] not in ("да", "нет"):
            raise ValueError("Unknown Moscow territory marker")
        result.append(
            MetroEntrance(
                integer(row["global_id"], positive=True),
                text(row["Name"]),
                text(row["NameOfStation"]),
                text(row["Line"]),
                lon,
                lat,
                text(row["ObjectStatus"]),
                row["OnTerritoryOfMoscow"] == "да",
            )
        )
    return tuple(result), metadata


def read_flows(path: Path):
    rows, metadata = source_rows(path, "62743")
    result = []
    quarters = {"I квартал": 1, "II квартал": 2, "III квартал": 3, "IV квартал": 4}
    for row in rows:
        if row["Quarter"] not in quarters:
            raise ValueError("Unknown quarter label")
        quarter = Quarter(row["Year"], quarters[row["Quarter"]])
        if quarter.shift(1).start > parse_time(metadata["retrieved_at"]):
            raise ValueError("Source contains an unfinished quarter")
        result.append(
            MetroFlow(
                integer(row["global_id"], positive=True),
                text(row["NameOfStation"]),
                text(row["Line"]),
                quarter,
                integer(row["IncomingPassengers"]),
                integer(row["OutgoingPassengers"]),
            )
        )
    return tuple(result), metadata


def encoded(document):
    return (
        json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def write_bundle(directory: Path, documents: dict, metadata: dict):
    """Never overwrite; manifest is the completion marker. Failed output is not readable."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", metadata["revision"]):
        raise ValueError("Invalid revision identifier")
    payloads = {}
    for name, document in documents.items():
        if Path(name).name != name or name == "manifest.json":
            raise ValueError("Only fixed flat output filenames are supported")
        payloads[name] = (
            b"".join(
                (
                    json.dumps(row, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n"
                ).encode("utf-8")
                for row in document
            )
            if name.endswith(".jsonl")
            else encoded(document)
        )
    manifest = metadata | {
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())}
    }
    if any(len(data) > MAX_BYTES for data in payloads.values()):
        raise ValueError("Prepared file would exceed the 50 MB reader limit")
    manifest_bytes = encoded(manifest)
    directory.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        with (directory / name).open("xb") as stream:
            stream.write(data)
    with (directory / "manifest.json").open("xb") as stream:
        stream.write(manifest_bytes)
    return manifest


def read_prepared(directory: Path):
    manifest_raw = read_bytes(directory / "manifest.json")
    manifest = strict_json(manifest_raw)
    if manifest["kind"] != "metro_research_bundle_v1" or set(manifest["files"]) != PREPARED_FILES:
        raise ValueError("Expected a complete metro research bundle")
    files = {}
    for name, expected in manifest["files"].items():
        raw = read_bytes(directory / name)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Prepared file checksum mismatch")
        files[name] = raw
    records = [strict_json(line) for line in files["quarters.jsonl"].splitlines()]
    points = tuple(
        QuarterlyPoint(
            r["series_id"],
            Quarter.parse(r["quarter"]),
            r["incoming"],
            r["outgoing"],
            r["missing_reason"],
        )
        for r in records
    )
    registry = strict_json(files["series.json"])
    ids = [r["series_id"] for r in registry]
    if len(ids) != len(set(ids)) or set(ids) != {p.series_id for p in points}:
        raise ValueError("Series registry and points disagree")
    return manifest, points, hashlib.sha256(manifest_raw).hexdigest()
