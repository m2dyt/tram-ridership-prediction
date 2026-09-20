"""Passenger mass balance; no database, network, randomness or model training."""

import copy
import math

from tram.domain.errors import DomainError
from tram.domain.series import nonnegative
from tram.domain.time import parse_time


def check(condition, message):
    if not condition:
        raise DomainError(message)


def allocation(count, stops, strategy):
    """Allocate one cohort to stop visits; weights are unconditional passenger masses."""
    nonnegative(count)
    check(bool(stops), "A cohort needs a future alighting stop")
    times = [parse_time(s["arrival_at"]).timestamp() for s in stops]
    check(all(a < b for a, b in zip(times, times[1:], strict=False)), "Stop times must increase")
    check(strategy in ("short", "uniform", "long"), "Unknown duration strategy")
    if len(stops) == 1:
        weights = [1.0]
    elif strategy == "short":
        weights = [1.0] + [0.0] * (len(stops) - 1)
    elif strategy == "long":
        weights = [0.0] * (len(stops) - 1) + [1.0]
    else:
        boundaries = [
            times[0],
            *[(a + b) / 2 for a, b in zip(times, times[1:], strict=False)],
            times[-1],
        ]
        weights = [
            (b - a) / (times[-1] - times[0])
            for a, b in zip(boundaries, boundaries[1:], strict=False)
        ]
    masses = [count * w for w in weights]
    masses[-1] += count - math.fsum(masses)
    return {str(stop["sequence"]): mass for stop, mass in zip(stops, masses, strict=True)}


def new_state(command):
    stops = command["stops"]
    check(2 <= len(stops) <= 500, "Trip must contain 2 to 500 stop visits")
    sequences = [s["sequence"] for s in stops]
    check(all(type(s) is int and s > 0 for s in sequences), "Invalid stop sequence")
    check(
        all(a < b for a, b in zip(sequences, sequences[1:], strict=False)),
        "Stop sequences must increase",
    )
    started = parse_time(command["started_at"])
    check(started < parse_time(stops[0]["arrival_at"]), "Trip starts before its first stop visit")
    nonnegative(command["initial_passengers"])
    if command["capacity"] is not None:
        nonnegative(command["capacity"])
        check(command["capacity"] > 0, "Capacity must be positive")
    check(
        command["terminal_clear"] is True,
        "An explicit terminal with mandatory alighting is required",
    )
    initial = allocation(command["initial_passengers"], stops, command["strategy"])
    return {
        "version": 0,
        "next_stop_index": 0,
        "last_event_at": command["started_at"],
        "remaining": command["initial_passengers"],
        "total_boardings": 0.0,
        "total_alightings": 0.0,
        "status": "active",
        "last_exchange": None,
        "cohorts": [
            {"id": "initial", "boarded": command["initial_passengers"], "allocations": initial}
        ],
        "value_kind": "estimated",
        "method": f"cohort_duration_{command['strategy']}_v1",
    }


def visit(trip, event):
    command, state = trip["plan"], copy.deepcopy(trip["state"])
    check(state["status"] == "active", "Trip is already completed")
    index = state["next_stop_index"]
    stop, future = command["stops"][index], command["stops"][index + 1 :]
    check(
        event["sequence"] == stop["sequence"],
        "Expected the next stop visit; replay corrections in a new trip",
    )
    at, available = parse_time(event["occurred_at"]), parse_time(event["available_at"])
    check(at > parse_time(state["last_event_at"]), "Stop visits must be strictly chronological")
    check(available >= at, "An event cannot be available before it occurred")
    boardings = event["boardings"]
    nonnegative(boardings)
    check(bool(future) or boardings == 0, "No boardings are allowed at the clearing terminal")
    # Delay changes arrival time, never causes alighting between stop visits.
    planned_alightings = math.fsum(
        c["allocations"].pop(str(stop["sequence"]), 0.0) for c in state["cohorts"]
    )
    observed = event.get("observed_alightings")
    if observed is not None:
        nonnegative(observed)
        check(observed <= state["remaining"] + 1e-8, "Alightings exceed passengers onboard")
        check(
            bool(future) or math.isclose(observed, state["remaining"], abs_tol=1e-8),
            "Terminal observation contradicts mandatory alighting",
        )
        # Known total exits do not identify individuals: redistribute remaining mass proportionally.
        surviving = max(0.0, state["remaining"] - observed)
        masses = [math.fsum(c["allocations"].values()) for c in state["cohorts"]]
        total = math.fsum(masses)
        if future and surviving:
            if total:
                for cohort in state["cohorts"]:
                    cohort["allocations"] = {
                        k: v * surviving / total for k, v in cohort["allocations"].items()
                    }
            else:
                state["cohorts"] = [
                    {
                        "id": "reconciled-" + event["event_id"],
                        "boarded": surviving,
                        "allocations": allocation(surviving, future, command["strategy"]),
                    }
                ]
        else:
            state["cohorts"] = []
        alightings = observed
    else:
        alightings = planned_alightings
    if boardings:
        state["cohorts"].append(
            {
                "id": event["event_id"],
                "boarded": boardings,
                "allocations": allocation(boardings, future, command["strategy"]),
            }
        )
    state["cohorts"] = [c for c in state["cohorts"] if math.fsum(c["allocations"].values()) > 1e-10]
    remaining = math.fsum(v for c in state["cohorts"] for v in c["allocations"].values())
    check(
        math.isclose(remaining, state["remaining"] - alightings + boardings, abs_tol=1e-7),
        "Passenger mass balance failed",
    )
    state.update(
        version=state["version"] + 1,
        next_stop_index=index + 1,
        last_event_at=at.isoformat(),
        remaining=remaining,
        status="active" if future else "completed",
        total_boardings=state["total_boardings"] + boardings,
        total_alightings=state["total_alightings"] + alightings,
        last_exchange={
            "sequence": stop["sequence"],
            "stop_id": stop["stop_id"],
            "boardings": boardings,
            "alightings": alightings,
            "alightings_kind": "observed" if observed is not None else "estimated",
        },
    )
    capacity = command["capacity"]
    state["occupancy_ratio"] = remaining / capacity if capacity else None
    state["flags"] = ["unverified_duration_assumption"] + (
        ["over_capacity"] if capacity and remaining > capacity else []
    )
    return {**trip, "state": state}
