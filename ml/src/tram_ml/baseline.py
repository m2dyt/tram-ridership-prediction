from collections.abc import Iterable
from datetime import datetime, timedelta

from tram.domain.errors import DomainError
from tram.domain.series import Observation, Prediction, SpatialKey
from tram.domain.time import (
    MOSCOW,
    Horizon,
    Interval,
    Resolution,
    add_months,
    advance,
    aligned,
    aware,
    forecast_window,
    intervals,
)


class SeasonalNaive:
    """Fixed rule, no training: latest completed same weekday/hour or seasonal month.

    The reference cycle is anchored to as_of. Monthly forecasts never use facts
    from the forecast period. Missing references are not filled with zero or
    silently replaced with an older, more favourable observation.
    """

    method = "seasonal_naive_v1"

    def predict(
        self,
        history: Iterable[Observation],
        series: tuple[SpatialKey, ...],
        window: Interval,
        horizon: Horizon,
        resolution: Resolution,
        as_of: datetime,
    ) -> tuple[Prediction, ...]:
        cutoff = aware(as_of)
        if forecast_window(window.start, horizon, resolution) != window:
            raise DomainError("Prediction window does not match its horizon")
        if cutoff > window.start:
            raise DomainError("as_of must not be later than forecast_start")
        if len({s.canonical for s in series}) != len(series):
            raise DomainError("Duplicate requested series")
        values: dict[tuple[str, datetime], Observation] = {}
        for observation in history:
            if (
                not aligned(observation.interval.start, resolution)
                or aware(advance(observation.interval.start, resolution))
                != observation.interval.end
            ):
                raise DomainError("History resolution does not match the prediction profile")
            if observation.available_at > cutoff or observation.interval.end > cutoff:
                continue
            key = (observation.spatial.canonical, observation.interval.start)
            if key in values:
                raise DomainError("Duplicate observations in one immutable dataset revision")
            values[key] = observation
        predictions = []
        for interval in intervals(window, resolution):
            reference = interval.start.astimezone(MOSCOW)
            while aware(advance(reference, resolution)) > cutoff:
                reference = (
                    add_months(reference, -12)
                    if horizon == Horizon.YEAR
                    else reference - timedelta(days=7)
                )
            for spatial in series:
                observation = values.get((spatial.canonical, aware(reference)))
                value = observation.value if observation else None
                predictions.append(
                    Prediction(
                        spatial,
                        interval,
                        value,
                        "reference_observation_unavailable" if value is None else None,
                        aware(reference),
                    )
                )
        return tuple(predictions)
