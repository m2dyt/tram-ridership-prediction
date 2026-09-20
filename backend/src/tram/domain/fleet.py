"""Steady-flow scenario, not a dispatcher order or an optimization model."""

import math

from tram.domain.occupancy import check
from tram.domain.series import nonnegative


def fleet_scenario(command):
    demand, capacity = command["passengers_per_hour"], command["vehicle_capacity"]
    target, cycle = command["target_ratio"], command["round_trip_minutes"]
    current, reserve = command["current_vehicles"], command["reserve_vehicles"]
    for value in (demand, capacity, target, cycle, current, reserve):
        nonnegative(value)
    check(capacity > 0 and 0 < target <= 1 and cycle > 0, "Invalid capacity, target ratio or cycle")
    check(type(current) is int and type(reserve) is int, "Vehicle counts must be integers")
    effective = capacity * target
    headway = 60 * effective / demand if demand else None
    required = math.ceil(demand * cycle / (60 * effective)) if demand else 0
    additional = max(0, required - current)
    available = current + reserve
    return {
        "required_vehicles": required,
        "additional_vehicles": additional,
        "available_vehicles": available,
        "reserve_shortfall": max(0, required - available),
        "feasible_with_reserve": required <= available,
        "maximum_headway_minutes": headway,
        "available_passengers_per_hour": available * 60 * effective / cycle,
        "assumptions": [
            "Demand is directional flow through the busiest segment per hour, not summed route boardings",
            "Round trip includes both directions and terminal layovers",
            "Homogeneous vehicles, steady demand, evenly spaced service; no dispatch feasibility optimization",
        ],
        "value_kind": "scenario",
    }
