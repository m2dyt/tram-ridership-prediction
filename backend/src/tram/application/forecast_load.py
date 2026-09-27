"""Expected load of a typical trip in one forecast hour, computed and never stored.

A stop-level forecast gives passengers boarding at each stop within the hour. One trip
takes an equal share of them (``trips_per_hour`` trips run in the hour) and the same
cohort engine as the occupancy journal decides where they alight. Nothing is written to
the journal: that one holds observed trips only.
"""

from datetime import timedelta

from tram.domain.occupancy import new_state, visit
from tram.domain.time import parse_time

# Nominal spacing of stop visits; it only orders cohorts for the duration strategy.
STOP_SPACING = timedelta(minutes=2)


def typical_trip_load(stops, boardings, start, trips_per_hour, capacity, strategy):
    """Per-stop exchange and onboard load of one trip.

    ``stops`` are the direction's stop visits in order, ``boardings`` maps a stop
    sequence to the forecast boardings of the whole hour (``None`` if missing).
    """
    start = parse_time(start) if isinstance(start, str) else start
    plan = {
        "started_at": start.isoformat(),
        "strategy": strategy,
        "capacity": capacity,
        "initial_passengers": 0.0,
        "terminal_clear": True,
        "stops": [
            {
                "sequence": stop["sequence"],
                "stop_id": stop["stop_id"],
                "arrival_at": (start + STOP_SPACING * (index + 1)).isoformat(),
            }
            for index, stop in enumerate(stops)
        ],
    }
    trip = {"plan": plan, "state": new_state(plan)}
    rows, flags = [], {"unverified_duration_assumption"}
    for index, stop in enumerate(plan["stops"]):
        hourly = boardings.get(stop["sequence"])
        if hourly is None:
            flags.add("missing_forecast_points")
            hourly = 0.0
        terminal = index == len(plan["stops"]) - 1
        if terminal and hourly:
            flags.add("terminal_boardings_excluded")
        per_trip = 0.0 if terminal else hourly / trips_per_hour
        trip = visit(
            trip,
            {
                "event_id": f"forecast-{stop['sequence']}",
                "sequence": stop["sequence"],
                "occurred_at": stop["arrival_at"],
                "available_at": stop["arrival_at"],
                "boardings": per_trip,
            },
        )
        state = trip["state"]
        rows.append(
            {
                "sequence": stop["sequence"],
                "stop_id": stop["stop_id"],
                "boardings": per_trip,
                "alightings": state["last_exchange"]["alightings"],
                "onboard": state["remaining"],
                "occupancy_ratio": state["occupancy_ratio"],
                "over_capacity": "over_capacity" in state["flags"],
            }
        )
    peak = max(rows, key=lambda row: row["onboard"])
    return {
        "stops": rows,
        "summary": {
            "boardings_per_trip": sum(row["boardings"] for row in rows),
            "peak_onboard": peak["onboard"],
            "peak_sequence": peak["sequence"],
            "peak_stop_id": peak["stop_id"],
            "peak_occupancy_ratio": peak["occupancy_ratio"],
            "over_capacity_stops": sum(row["over_capacity"] for row in rows),
        },
        "flags": sorted(flags),
    }
