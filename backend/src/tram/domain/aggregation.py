"""Time-weighted means per traversing vehicle, never a sum of occupancies."""

import math

from tram.domain.occupancy import check
from tram.domain.series import nonnegative


def weighted_occupancy(passages, interval, ratio=False):
    numerator, denominator, contributors = [], [], []
    for passage in passages:
        check(passage["start"] < passage["end"], "Invalid segment passage")
        overlap = (
            min(passage["end"], interval.end) - max(passage["start"], interval.start)
        ).total_seconds()
        if overlap <= 0:
            continue
        value = passage["remaining"]
        nonnegative(value)
        capacity = passage["capacity"]
        if ratio and capacity is None:
            return None, "capacity_unavailable", []
        if ratio:
            check(capacity > 0, "Invalid vehicle capacity")
            value /= capacity
        numerator.append(value * overlap)
        denominator.append(overlap)
        contributors.append(passage["trip_id"])
    if not denominator:
        return None, "no_completed_passages", []
    return math.fsum(numerator) / math.fsum(denominator), None, sorted(set(contributors))
