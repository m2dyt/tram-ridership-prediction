"""Prepare aggregate observations from committed stop journals; no inferred boardings."""

from tram.application.errors import ApplicationError
from tram.domain.aggregation import weighted_occupancy
from tram.domain.time import Interval, Resolution, intervals, parse_time


def export_occupancy(service, reads, trip_ids, revision, start, end, resolution, metric):
    if len(set(trip_ids)) != len(trip_ids):
        raise ApplicationError("VALIDATION_ERROR", "Repeated trip IDs would double-count passages")
    trips = [service.get(identity) for identity in trip_ids]
    if (
        not trips
        or len({t["plan"]["network_revision_id"] for t in trips}) != 1
        or len({t["plan"]["source_mode"] for t in trips}) != 1
    ):
        raise ApplicationError("VALIDATION_ERROR", "Trips must share one network and source mode")
    if metric not in ("occupancy", "occupancy_ratio"):
        raise ApplicationError("VALIDATION_ERROR", "Only occupancy metrics can be exported")
    window = Interval(parse_time(start), parse_time(end))
    buckets = intervals(window, Resolution(resolution))
    if window.end > service.clock.now():
        raise ApplicationError(
            "VALIDATION_ERROR", "Only completed aggregate intervals can be exported"
        )
    network = reads.network(trips[0]["plan"]["network_revision_id"])
    series = {}
    for trip in trips:
        plan = trip["plan"]
        route = next(r for r in network["routes"] if r["route"]["id"] == plan["route_id"])
        direction = next(d for d in route["directions"] if d["id"] == plan["direction_id"])
        visits = service.events(trip["id"])["items"]
        for segment in direction["segments"]:
            key = (plan["route_id"], plan["direction_id"], segment["id"])
            entry = series.setdefault(key, {"geometry": segment["geometry"], "passages": []})
            for left, right in zip(visits, visits[1:], strict=False):
                if (left["event"]["sequence"], right["event"]["sequence"]) != (
                    segment["from_sequence"],
                    segment["to_sequence"],
                ):
                    continue
                entry["passages"].append(
                    {
                        "trip_id": trip["id"],
                        "start": parse_time(left["event"]["occurred_at"]),
                        "end": parse_time(right["event"]["occurred_at"]),
                        "remaining": left["state_after"]["remaining"],
                        "capacity": plan["capacity"],
                    }
                )
    if not series:
        raise ApplicationError("VALIDATION_ERROR", "Published directions have no segments")
    now = service.clock.now().isoformat()
    profile_id = f"estimated-{metric}-segment-{resolution}"
    warnings = [
        "Unverified cohort-duration assumptions; only supplied trips contribute",
        "No completed passage is a missing value, not zero",
        "Not a complete fleet census",
        "trip_ids:" + ",".join(trip_ids),
    ]
    profile = {
        "id": profile_id,
        "metric": metric,
        "unit": "ratio" if metric == "occupancy_ratio" else "passengers",
        "spatial_level": "segment",
        "resolution": resolution,
        "route_ids": sorted({k[0] for k in series}),
        "history_start": start,
        "history_end": end,
        "aggregation_method": "vehicle_time_weighted_mean",
        "limitations": warnings,
    }
    caps = {
        "dataset_revision_id": revision,
        "network_revision_id": network["id"],
        "source_mode": trips[0]["plan"]["source_mode"],
        "timezone": "Europe/Moscow",
        "observation_profiles": [profile],
        "forecast_profiles": [],
        "max_page_size": 1000,
        "max_routes_per_run": 100,
        "warnings": warnings,
    }
    manifest = {
        "capabilities": caps,
        "network": network,
        "models": [],
        "series": [],
        "sources": [
            {
                "source": "telemetry",
                "source_mode": caps["source_mode"],
                "event_watermark": None,
                "ingested_at": now,
                "freshness": "unknown",
                "stale_after_seconds": None,
                "quality": {
                    "status": "unverified",
                    "coverage_ratio": None,
                    "flags": ["cohort_reconstruction"],
                },
            }
        ],
    }
    for (route, direction, segment), item in sorted(series.items()):
        item["spatial"] = {
            "level": "segment",
            "route_id": route,
            "direction_id": direction,
            "segment_id": segment,
            "stop_id": None,
            "stop_sequence": None,
        }
        manifest["series"].append(
            {
                "profile_id": profile_id,
                "spatial": item["spatial"],
                "geometry": item["geometry"],
                "coverage_start": start,
                "coverage_end": end,
            }
        )

    def records():
        for _, item in sorted(series.items()):
            for bucket in buckets:
                value, reason, contributors = weighted_occupancy(
                    item["passages"], bucket, metric == "occupancy_ratio"
                )
                yield {
                    "profile_id": profile_id,
                    "available_at": now,
                    "point": {
                        "spatial": item["spatial"],
                        "interval_start": bucket.start.isoformat(),
                        "interval_end": bucket.end.isoformat(),
                        "value": value,
                        "missing_reason": reason,
                        "value_kind": "estimated",
                        "estimation_method": "cohort_duration_vehicle_time_weighted_v1",
                        "quality": {
                            "status": "missing" if value is None else "unverified",
                            "coverage_ratio": None,
                            "flags": [
                                "unverified_duration_assumption",
                                "contributing_trips:" + str(len(contributors)),
                            ],
                        },
                    },
                }

    return manifest, records()
