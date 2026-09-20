import copy
from dataclasses import dataclass
from pathlib import Path

import yaml
from tram.application.mapping import spatial_from_document
from tram.domain.time import Interval, Resolution, intervals, parse_time
from tram.infrastructure.database import DatasetRow, NetworkRow, ObservationRow, SeriesRow
from tram.infrastructure.repository import point_columns

ROOT = Path(__file__).resolve().parents[1]
NOW = parse_time("2026-09-20T18:02:00+03:00")


@dataclass
class FrozenClock:
    value: object = NOW

    def now(self):
        return self.value


def fixture_bundle():
    spec = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    examples = spec["components"]["examples"]
    caps = copy.deepcopy(examples["Capabilities"]["value"])
    route_id = "demo-route-01"
    stop = {
        "id": "demo-stop-01",
        "name": "Демонстрационная остановка",
        "geometry": {"type": "Point", "coordinates": [37.62, 55.75]},
    }
    line = {"type": "LineString", "coordinates": [[37.62, 55.75], [37.621, 55.751]]}
    detail = {
        "network_revision_id": "demo-network-v1",
        "valid_at": "2026-09-21",
        "route": {
            "id": route_id,
            "number": "DEMO",
            "name": "Синтетический маршрут",
            "valid_from": "2020-01-01",
            "valid_to": None,
        },
        "directions": [
            {
                "id": "demo-outbound",
                "name": "Демонстрационное направление",
                "stops": [{"stop_id": stop["id"], "sequence": 1}],
                "segments": [],
                "geometry": line,
            }
        ],
        "stops": [stop],
        "warnings": ["Synthetic fixture"],
    }
    series, records, models = [], [], []
    for forecast in caps["forecast_profiles"]:
        observation = next(
            p for p in caps["observation_profiles"] if p["id"] == forecast["observation_profile_id"]
        )
        observation["history_start"] = (
            "2024-01-01T00:00:00+03:00"
            if observation["resolution"] == "month"
            else "2026-09-01T00:00:00+03:00"
        )
        spatial = {
            "level": observation["spatial_level"],
            "route_id": route_id,
            "direction_id": "demo-outbound" if observation["spatial_level"] == "stop" else None,
            "stop_id": stop["id"] if observation["spatial_level"] == "stop" else None,
            "stop_sequence": 1 if observation["spatial_level"] == "stop" else None,
            "segment_id": None,
        }
        series.append(
            {
                "profile_id": observation["id"],
                "spatial": spatial,
                "geometry": stop["geometry"] if spatial["level"] == "stop" else line,
                "coverage_start": observation["history_start"],
                "coverage_end": observation["history_end"],
            }
        )
        for i, interval in (
            enumerate(
                intervals(
                    Interval(
                        parse_time(observation["history_start"]),
                        parse_time(observation["history_end"]),
                    ),
                    Resolution(observation["resolution"]),
                )
            )
            if observation["resolution"] != "month"
            else enumerate(_monthly_history(observation))
        ):
            records.append(
                {
                    "profile_id": observation["id"],
                    "available_at": interval.end.isoformat(),
                    "point": {
                        "spatial": spatial,
                        "interval_start": interval.start.isoformat(),
                        "interval_end": interval.end.isoformat(),
                        "value": float(10 + i % 24),
                        "missing_reason": None,
                        "value_kind": "observed",
                        "estimation_method": None,
                        "quality": {
                            "status": "unverified",
                            "coverage_ratio": None,
                            "flags": ["synthetic_example"],
                        },
                    },
                }
            )
        models.append(
            {
                "profile_ids": [forecast["id"]],
                "model": {
                    "id": "baseline-" + forecast["horizon"],
                    "version": "1",
                    "method": "seasonal_naive_v1",
                    "training_history_end": observation["history_end"],
                    "feature_set_version": "calendar-v1",
                    "is_baseline": True,
                },
            }
        )
    manifest = {
        "capabilities": caps,
        "sources": examples["DataStatus"]["value"]["sources"],
        "models": models,
        "series": series,
        "network": {"id": "demo-network-v1", "routes": [detail]},
    }
    return manifest, records


def _monthly_history(profile):
    from tram.domain.time import advance

    start, end = parse_time(profile["history_start"]), parse_time(profile["history_end"])
    result = []
    while start < end:
        next_start = advance(start, Resolution.MONTH)
        result.append(Interval(start, next_start))
        start = next_start
    return result


def seed_trusted_fixture(sessions):
    """Only repository tests bypass the publication validator."""
    manifest, records = fixture_bundle()
    with sessions.begin() as session:
        session.add(NetworkRow(id=manifest["network"]["id"], document=manifest["network"]))
        session.flush()
        session.add(
            DatasetRow(
                id=manifest["capabilities"]["dataset_revision_id"],
                network_id=manifest["network"]["id"],
                published_at=NOW,
                manifest_hash="0" * 64,
                document={k: v for k, v in manifest.items() if k not in ("network", "series")},
            )
        )
        session.flush()
        for series in manifest["series"]:
            spatial = spatial_from_document(series["spatial"])
            session.add(
                SeriesRow(
                    dataset_id="demo-data-v1",
                    profile_id=series["profile_id"],
                    series_key=spatial.canonical,
                    route_id=spatial.route_id,
                    document=series,
                )
            )
        session.flush()
        for record in records:
            session.add(
                ObservationRow(
                    dataset_id="demo-data-v1",
                    profile_id=record["profile_id"],
                    available_at=parse_time(record["available_at"]),
                    **point_columns(record["point"]),
                )
            )
    return manifest
