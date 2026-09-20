"""Deterministic synthetic aggregate data; never presented as real passenger traffic."""

import json
from datetime import timedelta

from tram.domain.time import MOSCOW, Resolution, add_months, advance


def write_demo(directory, now):
    # Exclusive creation prevents accidental replacement of a user's prepared files.
    directory.mkdir(parents=True, exist_ok=False)
    midnight = now.astimezone(MOSCOW).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = midnight.replace(day=1)
    revision = "demo-data-v3-" + midnight.strftime("%Y%m%d")
    network_id, route_id = "demo-network-v3", "demo-route-01"
    warning = "Synthetic demonstration data; not real ridership or measured model accuracy"
    stops = [
        {
            "id": f"demo-stop-{i:02}",
            "name": f"Demo stop {i}",
            "geometry": {"type": "Point", "coordinates": xy},
        }
        for i, xy in enumerate(
            ([37.62, 55.75], [37.625, 55.755], [37.63, 55.76], [37.636, 55.766]), 1
        )
    ]
    line = {"type": "LineString", "coordinates": [s["geometry"]["coordinates"] for s in stops]}
    network = {
        "id": network_id,
        "routes": [
            {
                "network_revision_id": network_id,
                "valid_at": "2020-01-01",
                "route": {
                    "id": route_id,
                    "number": "DEMO",
                    "name": "Synthetic tram route",
                    "valid_from": "2020-01-01",
                    "valid_to": None,
                },
                "stops": stops,
                "warnings": [warning],
                "directions": [
                    {
                        "id": "demo-outbound",
                        "name": "Outbound",
                        "stops": [
                            {"stop_id": s["id"], "sequence": i} for i, s in enumerate(stops, 1)
                        ],
                        "segments": [
                            {
                                "id": f"demo-segment-{i:02}",
                                "from_stop_id": stops[i - 1]["id"],
                                "to_stop_id": stops[i]["id"],
                                "from_sequence": i,
                                "to_sequence": i + 1,
                                "geometry": {
                                    "type": "LineString",
                                    "coordinates": [
                                        stops[i - 1]["geometry"]["coordinates"],
                                        stops[i]["geometry"]["coordinates"],
                                    ],
                                },
                            }
                            for i in range(1, len(stops))
                        ],
                        "geometry": line,
                    }
                ],
            }
        ],
    }
    caps = {
        "dataset_revision_id": revision,
        "network_revision_id": network_id,
        "source_mode": "demo",
        "timezone": "Europe/Moscow",
        "observation_profiles": [],
        "forecast_profiles": [],
        "max_page_size": 1000,
        "max_routes_per_run": 100,
        "warnings": [warning],
    }
    manifest = {
        "capabilities": caps,
        "network": network,
        "sources": [
            {
                "source": "validations",
                "source_mode": "demo",
                "event_watermark": midnight.isoformat(),
                "ingested_at": midnight.isoformat(),
                "freshness": "unknown",
                "stale_after_seconds": None,
                "quality": {
                    "status": "unverified",
                    "coverage_ratio": None,
                    "flags": ["synthetic_example"],
                },
            }
        ],
        "models": [],
        "series": [],
    }
    requests = {}
    with (directory / "observations.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for horizon, resolution, history_start, history_end in (
            ("day", Resolution.HOUR, midnight - timedelta(days=28), midnight),
            ("month", Resolution.DAY, midnight - timedelta(days=60), midnight),
            ("year", Resolution.MONTH, add_months(month_start, -24), month_start),
        ):
            observation_id, profile_id = (
                f"demo-validations-route-{resolution.value}",
                f"demo-validations-{horizon}",
            )
            observed = {
                "id": observation_id,
                "metric": "validations",
                "unit": "validations",
                "spatial_level": "route",
                "resolution": resolution.value,
                "route_ids": [route_id],
                "history_start": history_start.isoformat(),
                "history_end": history_end.isoformat(),
                "aggregation_method": "sum",
                "limitations": [warning],
            }
            start = (
                add_months(month_start, 1) if horizon == "year" else midnight + timedelta(days=1)
            )
            profile = {
                k: observed[k]
                for k in (
                    "metric",
                    "unit",
                    "spatial_level",
                    "resolution",
                    "route_ids",
                    "aggregation_method",
                )
            }
            profile.update(
                {
                    "id": profile_id,
                    "observation_profile_id": observation_id,
                    "horizon": horizon,
                    "availability": "available",
                    "unavailable_reason": None,
                    "allowed_as_of_start": midnight.isoformat(),
                    "allowed_as_of_end": midnight.isoformat(),
                    "forecast_start_min": start.isoformat(),
                    "forecast_start_max": start.isoformat(),
                    "start_alignment": "month_start" if horizon == "year" else "local_midnight",
                    "evaluation_status": "pending",
                    "prediction_interval_available": False,
                    "limitations": [warning],
                }
            )
            caps["observation_profiles"].append(observed)
            caps["forecast_profiles"].append(profile)
            spatial = {
                "level": "route",
                "route_id": route_id,
                "direction_id": None,
                "stop_id": None,
                "stop_sequence": None,
                "segment_id": None,
            }
            manifest["series"].append(
                {
                    "profile_id": observation_id,
                    "spatial": spatial,
                    "geometry": line,
                    "coverage_start": history_start.isoformat(),
                    "coverage_end": history_end.isoformat(),
                }
            )
            manifest["models"].append(
                {
                    "profile_ids": [profile_id],
                    "model": {
                        "id": "seasonal-baseline-" + horizon,
                        "version": "1",
                        "method": "seasonal_naive_v1",
                        "training_history_end": history_end.isoformat(),
                        "feature_set_version": "calendar-v1",
                        "is_baseline": True,
                    },
                }
            )
            cursor = history_start
            while cursor < history_end:
                end = advance(cursor, resolution)
                value = (
                    (30 + cursor.hour * 2)
                    if resolution == Resolution.HOUR
                    else (900 + cursor.weekday() * 40)
                    if resolution == Resolution.DAY
                    else (27000 + cursor.month * 100)
                )
                record = {
                    "profile_id": observation_id,
                    "available_at": end.isoformat(),
                    "point": {
                        "spatial": spatial,
                        "interval_start": cursor.isoformat(),
                        "interval_end": end.isoformat(),
                        "value": value,
                        "missing_reason": None,
                        "value_kind": "observed",
                        "estimation_method": None,
                        "quality": {
                            "status": "unverified",
                            "coverage_ratio": 1,
                            "flags": ["synthetic_example"],
                        },
                    },
                }
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                cursor = end
            requests[horizon] = {
                "dataset_revision_id": revision,
                "profile_id": profile_id,
                "route_ids": [route_id],
                "as_of": midnight.isoformat(),
                "forecast_start": start.isoformat(),
            }
    started = midnight - timedelta(hours=12)
    trip_plan = {
        "trip_id": "demo-trip-" + midnight.strftime("%Y%m%d"),
        "vehicle_id": "demo-vehicle-01",
        "network_revision_id": network_id,
        "route_id": route_id,
        "direction_id": "demo-outbound",
        "started_at": started.isoformat(),
        "strategy": "uniform",
        "capacity": 100,
        "initial_passengers": 0,
        "terminal_clear": True,
        "source_mode": "demo",
        "stops": [
            {
                "sequence": i,
                "stop_id": stop["id"],
                "arrival_at": (started + timedelta(minutes=5 * i)).isoformat(),
            }
            for i, stop in enumerate(stops, 1)
        ],
    }
    with (directory / "trip-events.jsonl").open("x", encoding="utf-8") as stream:
        for stop, boardings in zip(trip_plan["stops"], [24, 12, 6, 0], strict=True):
            stream.write(
                json.dumps(
                    {
                        "event_id": f"demo-event-{stop['sequence']}",
                        "sequence": stop["sequence"],
                        "occurred_at": stop["arrival_at"],
                        "available_at": stop["arrival_at"],
                        "boardings": boardings,
                    }
                )
                + "\n"
            )
    for name, document in {
        "manifest.json": manifest,
        "trip-plan.json": trip_plan,
        "context-request.json": {
            "provider": "open-meteo",
            "latitude": 55.75,
            "longitude": 37.62,
            "from": now.isoformat(),
            "to": (now + timedelta(days=2)).isoformat(),
        },
        "evaluation-origins.json": {
            "day": (midnight - timedelta(days=1)).isoformat(),
            "month": add_months(midnight, -1).isoformat(),
            "year": add_months(month_start, -12).isoformat(),
        },
        **{f"request-{k}.json": v for k, v in requests.items()},
    }.items():
        (directory / name).write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return revision
