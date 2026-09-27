"""Convert the supplied Moscow tram labels and route catalog into an API bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from tram.domain.allocation import ESTIMATION_METHOD, HUB_BONUS, stop_shares

MOSCOW = ZoneInfo("Europe/Moscow")
ROUTE_NUMBERS = (1, 5, 7, 11, 12, 17, 25, 26, 28, 50)
DATA_START = date(2025, 1, 1)
DATA_END = date(2025, 11, 1)  # Exclusive; labels end on 2025-10-31.
PROFILE_ID = "competition-boardings-route-hour"
STOP_PROFILE_ID = "competition-boardings-stop-hour"
STOP_FORECAST_ID = "competition-forecast-stop-day"
# Seasonal naive needs the latest same weekday; two weeks keep the bundle small.
STOP_HISTORY_DAYS = 14
# Part of the revision hashes: a changed bundle layout must never reuse an old revision id.
BUNDLE_FORMAT = "route-hour+stop-hour+line-ids-v3"


def file_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def route_geometry(parts: object) -> dict | None:
    if not isinstance(parts, list):
        return None
    valid_parts = [
        [[float(point[0]), float(point[1])] for point in part]
        for part in parts
        if isinstance(part, list)
        and len(part) >= 2
        and all(isinstance(point, list) and len(point) >= 2 for point in part)
    ]
    if not valid_parts:
        return None
    if len(valid_parts) == 1:
        return {"type": "LineString", "coordinates": valid_parts[0]}
    return {"type": "MultiLineString", "coordinates": valid_parts}


def build_network(root: Path, network_id: str) -> tuple[dict, dict[str, dict], list[str]]:
    routes_path = root / "frontend/public/moscow_tram_routes.json"
    stops_path = root / "frontend/public/moscow_tram_stops.json"
    route_catalog = json.loads(routes_path.read_text(encoding="utf-8"))
    stop_catalog = json.loads(stops_path.read_text(encoding="utf-8"))
    network_routes = []
    geometries: dict[str, dict] = {}
    warnings = []

    for number in ROUTE_NUMBERS:
        route_id = str(number)
        geometry = route_geometry(route_catalog.get(route_id))
        if geometry is None:
            warnings.append(f"Для маршрута №{number} нет геометрии в справочнике.")
        else:
            geometries[route_id] = geometry

        route_stops = []
        for index, source_stop in enumerate(stop_catalog.get(route_id, []), start=1):
            coordinates = source_stop.get("geometry", {}).get("coordinates")
            if not isinstance(coordinates, list) or len(coordinates) < 2:
                continue
            stop_id = str(source_stop.get("id") or f"route-{number}-stop-{index}")
            route_stops.append(
                {
                    "id": stop_id,
                    "name": str(source_stop.get("name") or stop_id),
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(coordinates[0]), float(coordinates[1])],
                    },
                }
            )

        route_warnings = []
        if not route_stops:
            route_warnings.append("В исходном справочнике нет остановок этого маршрута.")
            warnings.extend(f"Маршрут №{number}: {warning}" for warning in route_warnings)

        network_routes.append(
            {
                "network_revision_id": network_id,
                "valid_at": DATA_START.isoformat(),
                "route": {
                    "id": route_id,
                    "number": route_id,
                    "name": f"Трамвай № {number} (Москва)",
                    "valid_from": DATA_START.isoformat(),
                    "valid_to": None,
                },
                "stops": route_stops,
                "warnings": route_warnings,
                "directions": [
                    {
                        "id": line_id(route_id),
                        "name": f"Линия маршрута № {number}",
                        "stops": [
                            {"stop_id": stop["id"], "sequence": index}
                            for index, stop in enumerate(route_stops, start=1)
                        ],
                        "segments": [],
                        "geometry": geometry,
                    }
                ],
            }
        )

    return {"id": network_id, "routes": network_routes}, geometries, warnings


def line_id(route_id: str) -> str:
    # The catalogue lists each route's stops as one line; occupancy trips need its id.
    return f"line-{route_id}"


def stop_spatial(route_id: str, stop_id: str, sequence: int) -> dict:
    return {
        "level": "stop",
        "route_id": route_id,
        "direction_id": line_id(route_id),
        "stop_id": stop_id,
        "stop_sequence": sequence,
        "segment_id": None,
    }


def build_bundle(data_dir: Path, output_dir: Path, project_root: Path) -> tuple[str, int]:
    labels_paths = [
        data_dir / "labels/labels_day_train.csv",
        data_dir / "labels/labels_day_test.csv",
    ]
    sample_path = data_dir / "test_submission.csv"
    static_paths = [
        project_root / "frontend/public/moscow_tram_routes.json",
        project_root / "frontend/public/moscow_tram_stops.json",
    ]
    missing = [path for path in [*labels_paths, sample_path, *static_paths] if not path.is_file()]
    if missing:
        raise FileNotFoundError("Required project data is missing: " + ", ".join(map(str, missing)))

    train, validation = (pd.read_csv(path, sep=";") for path in labels_paths)
    required = {"route", "date", "hour", "boardings"}
    for label, frame in (("train", train), ("validation", validation)):
        if not required <= set(frame.columns):
            raise ValueError(f"{label} labels must contain {sorted(required)}")
        frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date
        route_values = pd.to_numeric(frame["route"], errors="raise")
        hour_values = pd.to_numeric(frame["hour"], errors="raise")
        if (route_values % 1 != 0).any() or (hour_values % 1 != 0).any():
            raise ValueError(f"{label} labels contain fractional route numbers or hours")
        frame["route"] = route_values.astype(int)
        frame["hour"] = hour_values.astype(int)
        frame["boardings"] = pd.to_numeric(frame["boardings"], errors="raise")
        if frame.duplicated(["route", "date", "hour"]).any():
            raise ValueError(f"{label} labels contain duplicate route/date/hour keys")
        if not frame["route"].isin(ROUTE_NUMBERS).all():
            raise ValueError(f"{label} labels contain routes outside the official route list")
        if (
            not frame["hour"].between(0, 23).all()
            or frame["boardings"].isna().any()
            or not frame["boardings"].map(math.isfinite).all()
            or (frame["boardings"] < 0).any()
        ):
            raise ValueError(f"{label} labels contain invalid hours or negative boardings")

    labels = pd.concat([train, validation], ignore_index=True)
    if labels.empty or labels["date"].min() < DATA_START or labels["date"].max() >= DATA_END:
        raise ValueError("Label dates must fall within 2025-01-01 through 2025-10-31")
    if train["date"].max() >= date(2025, 9, 1) or validation["date"].min() < date(2025, 9, 1):
        raise ValueError("Training and validation labels do not match the documented 2025 split")

    sample = pd.read_csv(sample_path, sep=";")
    if not {"route", "date", "hour", "prediction"} <= set(sample.columns):
        raise ValueError("test_submission.csv has an unexpected schema")

    label_hash = file_digest(labels_paths)
    network_hash = hashlib.sha256(
        f"{file_digest(static_paths)}:{BUNDLE_FORMAT}".encode()
    ).hexdigest()[:12]
    dataset_hash = hashlib.sha256(
        f"{label_hash}:{network_hash}:{BUNDLE_FORMAT}".encode()
    ).hexdigest()[:12]
    dataset_id = f"competition-2025-{dataset_hash}"
    network_id = f"moscow-tram-{network_hash}"
    network, geometries, network_warnings = build_network(project_root, network_id)

    history_start = datetime.combine(DATA_START, time.min, MOSCOW)
    history_end = datetime.combine(DATA_END, time.min, MOSCOW)
    as_of_start = history_start + timedelta(days=28)
    stop_routes = {
        route["route"]["id"]: [position["stop_id"] for position in route["directions"][0]["stops"]]
        for route in network["routes"]
        if route["directions"][0]["stops"]
    }
    shares = stop_shares(stop_routes)
    stop_ids = {route["route"]["id"]: route["stops"] for route in network["routes"]}
    stop_history_start = history_end - timedelta(days=STOP_HISTORY_DAYS)
    stop_limitations = [
        "Валидации не содержат остановку посадки: значения остановок — оценка, а не измерение.",
        "Почасовые посадки маршрута распределены по его остановкам пропорционально весу: 1 за "
        f"позицию и +{HUB_BONUS} за каждый другой маршрут, обслуживающий остановку "
        "(пересадочный узел). Сумма по остановкам равна итогу маршрута.",
        f"История по остановкам — последние {STOP_HISTORY_DAYS} суток; маршрут №5 без остановок "
        "в справочнике не входит в профиль.",
    ]
    all_buckets = (DATA_END - DATA_START).days * 24 * len(ROUTE_NUMBERS)
    counts_by_route = labels.groupby("route").size().to_dict()
    coverage_ratio = len(labels) / all_buckets
    latest_event = max(
        datetime.combine(row.date, time(hour=int(row.hour)), MOSCOW) + timedelta(hours=1)
        for row in labels.itertuples(index=False)
    )
    limitations = [
        "История содержит почасовые агрегаты из labels_day_train.csv и labels_day_test.csv.",
        "Интервалы без исходной строки сохранены как пропуски; обучающий конвейер модели трактует отсутствующие метки как нулевые оплаты.",
        "Справочник не содержит остановок маршрута №5.",
    ]
    manifest = {
        "capabilities": {
            "dataset_revision_id": dataset_id,
            "network_revision_id": network_id,
            "source_mode": "batch",
            "timezone": "Europe/Moscow",
            "observation_profiles": [
                {
                    "id": PROFILE_ID,
                    "metric": "boardings",
                    "unit": "passengers",
                    "spatial_level": "route",
                    "resolution": "hour",
                    "route_ids": [str(number) for number in ROUTE_NUMBERS],
                    "history_start": history_start.isoformat(),
                    "history_end": history_end.isoformat(),
                    "aggregation_method": "sum",
                    "limitations": limitations,
                },
                {
                    "id": STOP_PROFILE_ID,
                    "metric": "boardings",
                    "unit": "passengers",
                    "spatial_level": "stop",
                    "resolution": "hour",
                    "route_ids": list(stop_routes),
                    "history_start": stop_history_start.isoformat(),
                    "history_end": history_end.isoformat(),
                    "aggregation_method": "sum",
                    "limitations": stop_limitations,
                },
            ],
            "forecast_profiles": [
                {
                    "id": "competition-forecast-route-day",
                    "metric": "boardings",
                    "unit": "passengers",
                    "spatial_level": "route",
                    "resolution": "hour",
                    "route_ids": [str(number) for number in ROUTE_NUMBERS],
                    "aggregation_method": "sum",
                    "observation_profile_id": PROFILE_ID,
                    "horizon": "day",
                    "availability": "available",
                    "unavailable_reason": None,
                    "allowed_as_of_start": as_of_start.isoformat(),
                    "allowed_as_of_end": history_end.isoformat(),
                    "forecast_start_min": history_end.isoformat(),
                    "forecast_start_max": history_end.isoformat(),
                    "start_alignment": "local_midnight",
                    "evaluation_status": "pending",
                    "prediction_interval_available": False,
                    "limitations": [
                        "Для API доступен почасовой прогноз на одни сутки.",
                        "Прогноз на ноябрь и декабрь для конкурсной отправки строится отдельной командой обучения.",
                    ],
                },
                {
                    "id": STOP_FORECAST_ID,
                    "metric": "boardings",
                    "unit": "passengers",
                    "spatial_level": "stop",
                    "resolution": "hour",
                    "route_ids": list(stop_routes),
                    "aggregation_method": "sum",
                    "observation_profile_id": STOP_PROFILE_ID,
                    "horizon": "day",
                    "availability": "available",
                    "unavailable_reason": None,
                    "allowed_as_of_start": (stop_history_start + timedelta(days=7)).isoformat(),
                    "allowed_as_of_end": history_end.isoformat(),
                    "forecast_start_min": history_end.isoformat(),
                    "forecast_start_max": history_end.isoformat(),
                    "start_alignment": "local_midnight",
                    "evaluation_status": "pending",
                    "prediction_interval_available": False,
                    "limitations": [
                        "Почасовой прогноз на сутки по остановкам — сезонная база на оценённом "
                        "распределении; обученная модель маршрута здесь не применяется.",
                        *stop_limitations,
                    ],
                },
            ],
            "max_page_size": 1000,
            "max_routes_per_run": 100,
            "warnings": network_warnings,
        },
        "network": network,
        "sources": [
            {
                "source": "validations",
                "source_mode": "batch",
                "event_watermark": latest_event.isoformat(),
                # Deterministic: rebuilding the same labels must yield identical content,
                # otherwise re-importing an existing revision is rejected.
                "ingested_at": history_end.isoformat(),
                "freshness": "unknown",
                "stale_after_seconds": None,
                "quality": {
                    "status": "partial" if coverage_ratio < 1 else "ok",
                    "coverage_ratio": coverage_ratio,
                    "flags": ["competition_labels", "missing_buckets_preserved"],
                },
            }
        ],
        "models": [
            {
                "profile_ids": ["competition-forecast-route-day", STOP_FORECAST_ID],
                "model": {
                    "id": "seasonal-baseline-competition",
                    "version": "1",
                    "method": "seasonal_naive_v1",
                    "is_baseline": True,
                    "feature_set_version": "calendar_v1",
                    "training_history_end": history_end.isoformat(),
                },
            }
        ],
        "series": [
            {
                "profile_id": PROFILE_ID,
                "spatial": {
                    "level": "route",
                    "route_id": str(number),
                    "direction_id": None,
                    "stop_id": None,
                    "stop_sequence": None,
                    "segment_id": None,
                },
                "geometry": geometries.get(str(number)),
                "coverage_start": history_start.isoformat(),
                "coverage_end": history_end.isoformat(),
            }
            for number in ROUTE_NUMBERS
        ]
        + [
            {
                "profile_id": STOP_PROFILE_ID,
                "spatial": stop_spatial(route_id, stop_id, sequence),
                "geometry": stop_ids[route_id][sequence - 1]["geometry"],
                "coverage_start": stop_history_start.isoformat(),
                "coverage_end": history_end.isoformat(),
            }
            for route_id, stops in stop_routes.items()
            for sequence, stop_id in enumerate(stops, start=1)
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    record_count = 0
    observed = {
        (int(row.route), row.date, int(row.hour)): float(row.boardings)
        for row in labels.itertuples(index=False)
    }
    with (output_dir / "observations.jsonl").open("w", encoding="utf-8") as stream:
        current_date = DATA_START
        while current_date < DATA_END:
            for hour in range(24):
                interval_start = datetime.combine(current_date, time(hour), MOSCOW)
                interval_end = interval_start + timedelta(hours=1)
                for number in ROUTE_NUMBERS:
                    value = observed.get((number, current_date, hour))
                    missing = value is None
                    record = {
                        "profile_id": PROFILE_ID,
                        "available_at": interval_end.isoformat(),
                        "point": {
                            "spatial": {
                                "level": "route",
                                "route_id": str(number),
                                "direction_id": None,
                                "stop_id": None,
                                "stop_sequence": None,
                                "segment_id": None,
                            },
                            "interval_start": interval_start.isoformat(),
                            "interval_end": interval_end.isoformat(),
                            "value": value,
                            "value_kind": "observed",
                            "estimation_method": None,
                            "missing_reason": "not_present_in_source" if missing else None,
                            "quality": {
                                "status": "missing" if missing else "ok",
                                "coverage_ratio": 0.0 if missing else 1.0,
                                "flags": ["missing_source_bucket"] if missing else [],
                            },
                        },
                    }
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    record_count += 1
            current_date += timedelta(days=1)
        current_date = stop_history_start.date()
        while current_date < DATA_END:
            for hour in range(24):
                interval_start = datetime.combine(current_date, time(hour), MOSCOW)
                interval_end = interval_start + timedelta(hours=1)
                for route_id, stops in stop_routes.items():
                    total = observed.get((int(route_id), current_date, hour))
                    for sequence, (stop_id, share) in enumerate(
                        zip(stops, shares[route_id], strict=True), start=1
                    ):
                        missing = total is None
                        record = {
                            "profile_id": STOP_PROFILE_ID,
                            "available_at": interval_end.isoformat(),
                            "point": {
                                "spatial": stop_spatial(route_id, stop_id, sequence),
                                "interval_start": interval_start.isoformat(),
                                "interval_end": interval_end.isoformat(),
                                "value": None if missing else round(total * share, 6),
                                "value_kind": "estimated",
                                "estimation_method": ESTIMATION_METHOD,
                                "missing_reason": "not_present_in_source" if missing else None,
                                "quality": {
                                    "status": "missing" if missing else "unverified",
                                    "coverage_ratio": 0.0 if missing else None,
                                    "flags": ["missing_source_bucket"]
                                    if missing
                                    else ["estimated_stop_split"],
                                },
                            },
                        }
                        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                        record_count += 1
            current_date += timedelta(days=1)

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Bundle: {output_dir}")
    print(f"Dataset revision: {dataset_id}")
    print(f"Network revision: {network_id}")
    print(f"Routes: {len(ROUTE_NUMBERS)}; stop-level routes: {len(stop_routes)}")
    print(f"Hourly records (routes + estimated stops): {record_count:,}")
    missing_route_five = all_buckets // len(ROUTE_NUMBERS) - counts_by_route.get(5, 0)
    print(f"Source coverage: {coverage_ratio:.2%}; missing route-5 buckets: {missing_route_five:,}")
    return dataset_id, record_count


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=project_root / "dataset")
    parser.add_argument("--output-dir", type=Path, default=project_root / "data/competition_bundle")
    parser.add_argument("--project-root", type=Path, default=project_root)
    args = parser.parse_args()
    build_bundle(args.data_dir, args.output_dir, args.project_root)


if __name__ == "__main__":
    main()
