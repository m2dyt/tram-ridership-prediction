import json
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from tram.domain.errors import DomainError
from tram.domain.time import Interval, aware


class Metric(StrEnum):
    VALIDATIONS = "validations"
    BOARDINGS = "boardings"
    OCCUPANCY = "occupancy"
    OCCUPANCY_RATIO = "occupancy_ratio"


class SpatialLevel(StrEnum):
    ROUTE = "route"
    ROUTE_DIRECTION = "route_direction"
    STOP = "stop"
    SEGMENT = "segment"


def nonnegative(value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise DomainError("Value must be finite and non-negative")


@dataclass(frozen=True)
class SpatialKey:
    level: SpatialLevel
    route_id: str
    direction_id: str | None = None
    stop_id: str | None = None
    stop_sequence: int | None = None
    segment_id: str | None = None

    def __post_init__(self) -> None:
        for value in (self.route_id, self.direction_id, self.stop_id, self.segment_id):
            if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 128):
                raise DomainError("Identifiers must contain 1–128 characters")
        if not self.route_id:
            raise DomainError("route_id is required")
        if self.stop_sequence is not None and (
            isinstance(self.stop_sequence, bool)
            or not isinstance(self.stop_sequence, int)
            or self.stop_sequence < 1
        ):
            raise DomainError("stop_sequence must be a positive integer")
        if self.level == SpatialLevel.ROUTE and self.direction_id is not None:
            raise DomainError("Route aggregates cannot contain a direction")
        if self.level == SpatialLevel.ROUTE_DIRECTION and self.direction_id is None:
            raise DomainError("Direction aggregate requires direction_id")
        if self.level == SpatialLevel.STOP:
            if self.stop_id is None or self.stop_sequence is None or self.segment_id is not None:
                raise DomainError(
                    "Stop series requires stop_id/sequence and cannot contain segment_id"
                )
        elif self.stop_id is not None or self.stop_sequence is not None:
            raise DomainError("Only stop series may contain stop identifiers")
        if (self.segment_id is not None) != (self.level == SpatialLevel.SEGMENT):
            raise DomainError("segment_id is required exclusively for segment series")

    @property
    def canonical(self) -> str:
        # JSON encodes missing dimensions explicitly and avoids delimiter collisions.
        return json.dumps(
            [
                self.level.value,
                self.route_id,
                self.direction_id,
                self.stop_id,
                self.stop_sequence,
                self.segment_id,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class Observation:
    spatial: SpatialKey
    interval: Interval
    available_at: datetime
    value: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "available_at", aware(self.available_at))
        if self.available_at < self.interval.end:
            raise DomainError("A completed aggregate cannot be available before its interval ends")
        if self.value is not None:
            nonnegative(self.value)


@dataclass(frozen=True)
class Prediction:
    spatial: SpatialKey
    interval: Interval
    value: float | None
    missing_reason: str | None
    reference_start: datetime | None

    def __post_init__(self) -> None:
        if self.value is not None:
            nonnegative(self.value)
        if (self.value is None) != bool(self.missing_reason):
            raise DomainError(
                "Missing predictions must have a reason; nonmissing predictions must not"
            )
