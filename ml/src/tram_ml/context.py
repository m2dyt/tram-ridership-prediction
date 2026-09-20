"""As-of context joins for future models. No fitting and no heuristic demand correction."""

from math import asin, cos, radians, sin, sqrt

from tram.domain.time import parse_time


def distance_m(a, b):
    lon1, lat1, lon2, lat2 = map(radians, [*a, *b])
    term = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * asin(sqrt(min(1, max(0, term))))


def context_features(snapshots, at, as_of, point, radius_m=800):
    """Use the latest eligible snapshot per provider, kind and requested location."""
    eligible = {}
    for snap in snapshots:
        if snap["status"] != "succeeded" or parse_time(snap["available_at"]) > as_of:
            continue
        request = snap.get("request", {})
        key = (
            snap["provider"],
            snap["kind"],
            request.get("latitude"),
            request.get("longitude"),
            snap.get("source_url"),
        )
        if key not in eligible or parse_time(snap["available_at"]) > parse_time(
            eligible[key]["available_at"]
        ):
            eligible[key] = snap
    weather, events, geo, used = [], set(), set(), []
    for snap in eligible.values():
        used.append(snap["id"])
        for row in snap["records"]:
            coords = row.get("coordinates")
            if coords is None:
                continue
            distance = distance_m(point, coords)
            if snap["kind"] == "weather" and parse_time(row["time"]) == at and distance <= 25000:
                weather.append((distance, snap["provider"], row))
            if (
                snap["kind"] == "events"
                and distance <= radius_m
                and parse_time(row["start"]) <= at < parse_time(row["end"])
            ):
                events.add((snap["provider"], row["id"]))
            if snap["kind"] == "geo" and distance <= radius_m:
                geo.add((snap["source_url"], row["id"]))
    weather.sort(key=lambda r: (r[0], r[1]))
    return {
        "weather": weather[0][2] if weather else None,
        "nearby_catalogue_events": len(events),
        "nearby_geo_objects": len(geo),
        "snapshot_ids": sorted(used),
        "warnings": [
            "Catalogue event counts are not passenger counts",
            "Missing snapshots do not prove absence of events",
        ],
    }
