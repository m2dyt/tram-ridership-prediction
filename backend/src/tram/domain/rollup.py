"""Roll forecast points up over time buckets and spatial units without inventing values.

Additive metrics (``aggregation_method == "sum"``: validations, boardings) are summed over
series and intervals. Non-additive metrics (occupancy averages) are never summed: they are
averaged, weighting each point by its interval duration so months of unequal length count
proportionally. A missing point is never treated as zero; it lowers the coverage instead.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from tram.domain.errors import DomainError
from tram.domain.series import SpatialKey, SpatialLevel
from tram.domain.time import MOSCOW, Interval, Resolution, advance, aware

ADDITIVE_METHOD = "sum"


class GroupBy(StrEnum):
    NONE = "none"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    ROUTE = "route"
    DIRECTION = "direction"
    STOP = "stop"
    SEGMENT = "segment"


TIME_GROUPS = {
    GroupBy.HOUR: Resolution.HOUR,
    GroupBy.DAY: Resolution.DAY,
    GroupBy.MONTH: Resolution.MONTH,
}
_GRAIN_ORDER = (Resolution.HOUR, Resolution.DAY, Resolution.MONTH)
# Spatial levels that carry the identifiers a spatial grouping needs.
_SPATIAL_SUPPORT = {
    GroupBy.ROUTE: set(SpatialLevel),
    GroupBy.DIRECTION: {SpatialLevel.ROUTE_DIRECTION, SpatialLevel.STOP, SpatialLevel.SEGMENT},
    GroupBy.STOP: {SpatialLevel.STOP},
    GroupBy.SEGMENT: {SpatialLevel.SEGMENT},
}
_KEY_FIELDS = ("route_id", "direction_id", "stop_id", "stop_sequence", "segment_id")


def check_group_by(group_by: GroupBy, resolution: Resolution, level: SpatialLevel) -> None:
    """Reject groupings finer than the stored grid or absent from the spatial level."""
    if group_by in TIME_GROUPS:
        if _GRAIN_ORDER.index(TIME_GROUPS[group_by]) < _GRAIN_ORDER.index(resolution):
            raise DomainError(f"Forecast resolution is {resolution.value}; cannot group finer")
    elif group_by != GroupBy.NONE and level not in _SPATIAL_SUPPORT[group_by]:
        raise DomainError(f"Spatial level {level.value} has no {group_by.value} units")


def bucket_start(value: datetime, grain: Resolution) -> datetime:
    local = aware(value).astimezone(MOSCOW)
    local = local.replace(minute=0, second=0, microsecond=0)
    if grain in (Resolution.DAY, Resolution.MONTH):
        local = local.replace(hour=0)
    if grain == Resolution.MONTH:
        local = local.replace(day=1)
    return local


def _group_key(group_by: GroupBy, spatial: SpatialKey, interval: Interval, window: Interval):
    if group_by in TIME_GROUPS:
        grain = TIME_GROUPS[group_by]
        start = bucket_start(interval.start, grain)
        end = aware(advance(start, grain))
        return ("time", max(aware(start), window.start), min(end, window.end))
    keep = {
        GroupBy.ROUTE: ("route_id",),
        GroupBy.DIRECTION: ("route_id", "direction_id"),
        GroupBy.STOP: ("route_id", "direction_id", "stop_id", "stop_sequence"),
        GroupBy.SEGMENT: ("route_id", "direction_id", "segment_id"),
    }[group_by]
    return ("space",) + tuple(
        getattr(spatial, name) if name in keep else None for name in _KEY_FIELDS
    )


@dataclass
class _Cell:
    values: list = field(default_factory=list)
    missing: int = 0


@dataclass
class _Accumulator:
    additive: bool
    cells: dict = field(default_factory=lambda: defaultdict(_Cell))
    series: set = field(default_factory=set)
    weighted: list = field(default_factory=list)
    weights: list = field(default_factory=list)

    def add(self, series_key: str, interval: Interval, value: float | None) -> None:
        cell = self.cells[(interval.start, interval.end)]
        self.series.add(series_key)
        if value is None:
            cell.missing += 1
            return
        seconds = (interval.end - interval.start).total_seconds()
        cell.values.append(value)
        self.weighted.append(value * seconds)
        self.weights.append(seconds)

    def interval_value(self, cell: _Cell) -> float | None:
        if not cell.values:
            return None
        total = math.fsum(cell.values)
        return total if self.additive else total / len(cell.values)

    def result(self) -> dict:
        points = sum(len(c.values) + c.missing for c in self.cells.values())
        missing = sum(c.missing for c in self.cells.values())
        per_interval = [
            (start, end, self.interval_value(cell))
            for (start, end), cell in sorted(self.cells.items())
        ]
        known = [item for item in per_interval if item[2] is not None]
        if not self.weights:
            value = None
        elif self.additive:
            value = math.fsum(v for c in self.cells.values() for v in c.values)
        else:
            value = math.fsum(self.weighted) / math.fsum(self.weights)
        peak = max(known, key=lambda item: item[2]) if known else None
        low = min(known, key=lambda item: item[2]) if known else None
        coverage = (points - missing) / points if points else None
        flags = []
        if not points:
            flags.append("empty_selection")
        elif missing:
            flags.append("missing_forecast_points")
        return {
            "value": value,
            "interval_mean": math.fsum(v for *_, v in known) / len(known) if known else None,
            "interval_min": low[2] if low else None,
            "interval_max": peak[2] if peak else None,
            "peak_interval_start": peak[0].isoformat() if peak else None,
            "peak_interval_end": peak[1].isoformat() if peak else None,
            "series_count": len(self.series),
            "interval_count": len(per_interval),
            "point_count": points,
            "missing_count": missing,
            "quality": {
                "status": "missing" if value is None else "partial" if missing else "ok",
                "coverage_ratio": coverage,
                "flags": flags,
            },
        }


class ForecastRollup:
    """Stream forecast points once; keep only per-interval accumulators, never raw pages."""

    def __init__(self, window: Interval, aggregation_method: str, group_by: GroupBy):
        self.window, self.group_by = window, group_by
        self.additive = aggregation_method == ADDITIVE_METHOD
        self.summary = _Accumulator(self.additive)
        self.groups: dict = defaultdict(lambda: _Accumulator(self.additive))

    @property
    def statistic(self) -> str:
        return "sum" if self.additive else "mean"

    def add(self, spatial: SpatialKey, interval: Interval, value: float | None) -> None:
        if interval.start < self.window.start or interval.end > self.window.end:
            raise DomainError("Forecast point lies outside the aggregation window")
        self.summary.add(spatial.canonical, interval, value)
        if self.group_by != GroupBy.NONE:
            key = _group_key(self.group_by, spatial, interval, self.window)
            self.groups[key].add(spatial.canonical, interval, value)

    def result(self) -> dict:
        groups = []
        for key, accumulator in self.groups.items():
            if key[0] == "time":
                identity = {
                    "interval_start": key[1].isoformat(),
                    "interval_end": key[2].isoformat(),
                    **dict.fromkeys(_KEY_FIELDS),
                }
            else:
                identity = {
                    "interval_start": None,
                    "interval_end": None,
                    **dict(zip(_KEY_FIELDS, key[1:], strict=True)),
                }
            groups.append({**identity, **accumulator.result()})
        groups.sort(key=_group_order)
        return {"statistic": self.statistic, "summary": self.summary.result(), "groups": groups}


def _group_order(group: dict):
    return (
        group["interval_start"] or "",
        group["route_id"] or "",
        group["direction_id"] or "",
        group["stop_sequence"] or 0,
        group["stop_id"] or "",
        group["segment_id"] or "",
    )
