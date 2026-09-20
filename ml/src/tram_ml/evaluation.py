import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from tram.domain.errors import DomainError
from tram.domain.series import nonnegative
from tram.domain.time import Horizon, Interval, Resolution, aware, forecast_window


@dataclass(frozen=True)
class Scores:
    sample_count: int
    excluded_count: int
    mae: float | None
    wape: float | None
    sum_actual: float
    wape_unavailable_reason: str | None


def score(actual: Sequence[float | None], predicted: Sequence[float | None]) -> Scores:
    if len(actual) != len(predicted):
        raise DomainError("Actual and prediction lengths differ")
    pairs: list[tuple[float, float]] = []
    for observed, prediction in zip(actual, predicted, strict=True):
        for value in (observed, prediction):
            if value is not None:
                nonnegative(value)
        if observed is not None and prediction is not None:
            pairs.append((observed, prediction))
    count = len(pairs)
    actual_sum = math.fsum(a for a, _ in pairs)
    error_sum = math.fsum(abs(a - p) for a, p in pairs)
    reason = "empty_sample" if count == 0 else "zero_actual_sum" if actual_sum == 0 else None
    return Scores(
        count,
        len(actual) - count,
        error_sum / count if count else None,
        error_sum / actual_sum if actual_sum > 0 else None,
        actual_sum,
        reason,
    )


@dataclass(frozen=True)
class TemporalFold:
    training: Interval
    test: Interval
    as_of: datetime


def temporal_folds(
    history: Interval, origins: Sequence[datetime], horizon: Horizon, resolution: Resolution
) -> tuple[TemporalFold, ...]:
    """Require complete horizons. Never truncate a year to the history available."""
    folds = []
    last = None
    for origin in origins:
        cutoff = aware(origin)
        if last is not None and cutoff <= last:
            raise DomainError("Origins must be unique and increasing")
        test = forecast_window(cutoff, horizon, resolution)
        if cutoff <= history.start or test.end > history.end:
            raise DomainError("Insufficient history for a complete training/test split")
        folds.append(TemporalFold(Interval(history.start, cutoff), test, cutoff))
        last = cutoff
    return tuple(folds)
