from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from tram.domain.errors import DomainError

MOSCOW = ZoneInfo("Europe/Moscow")


class Horizon(StrEnum):
    DAY = "day"
    MONTH = "month"
    YEAR = "year"


class Resolution(StrEnum):
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainError("Timestamp must have an explicit UTC offset")
    return value.astimezone(UTC)


def parse_time(value: str) -> datetime:
    try:
        return aware(datetime.fromisoformat(value.upper().replace("Z", "+00:00")))
    except (TypeError, ValueError) as exc:
        raise DomainError("Expected an RFC 3339 timestamp with an offset") from exc


def add_months(value: datetime, months: int) -> datetime:
    local = aware(value).astimezone(MOSCOW)
    year, month_zero = divmod(local.year * 12 + local.month - 1 + months, 12)
    if not 1 <= year <= 9999:
        raise DomainError("Date outside supported calendar range")
    month = month_zero + 1
    return local.replace(year=year, month=month, day=min(local.day, monthrange(year, month)[1]))


def aligned(value: datetime, resolution: Resolution) -> bool:
    local = aware(value).astimezone(MOSCOW)
    if local.minute or local.second or local.microsecond:
        return False
    if resolution in (Resolution.DAY, Resolution.MONTH) and local.hour:
        return False
    return resolution != Resolution.MONTH or local.day == 1


def advance(value: datetime, resolution: Resolution) -> datetime:
    local = aware(value).astimezone(MOSCOW)
    if resolution == Resolution.MONTH:
        return add_months(local, 1)
    return local + (timedelta(hours=1) if resolution == Resolution.HOUR else timedelta(days=1))


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", aware(self.start))
        object.__setattr__(self, "end", aware(self.end))
        if self.start >= self.end:
            raise DomainError("Interval start must precede its exclusive end")

    def validate_grid(self, resolution: Resolution, *, max_days: int = 366) -> None:
        if not aligned(self.start, resolution) or not aligned(self.end, resolution):
            raise DomainError("Interval boundaries must align with the profile resolution")
        if self.end.astimezone(MOSCOW) - self.start.astimezone(MOSCOW) > timedelta(days=max_days):
            raise DomainError(f"Requested interval exceeds {max_days} days")


def forecast_window(start: datetime, horizon: Horizon, resolution: Resolution) -> Interval:
    expected = {
        Horizon.DAY: Resolution.HOUR,
        Horizon.MONTH: Resolution.DAY,
        Horizon.YEAR: Resolution.MONTH,
    }
    if resolution != expected[horizon]:
        raise DomainError("Unsupported horizon/resolution profile")
    if not aligned(start, Resolution.MONTH if horizon == Horizon.YEAR else Resolution.DAY):
        raise DomainError(
            "Forecast must start at Moscow midnight (month start for annual forecasts)"
        )
    local = aware(start).astimezone(MOSCOW)
    end = (
        local + timedelta(days=1)
        if horizon == Horizon.DAY
        else add_months(local, 1 if horizon == Horizon.MONTH else 12)
    )
    return Interval(local, end)


def intervals(window: Interval, resolution: Resolution) -> tuple[Interval, ...]:
    window.validate_grid(resolution)
    result = []
    start = window.start
    while start < window.end:
        end = aware(advance(start, resolution))
        if end > window.end:
            raise DomainError("Window contains a partial interval")
        result.append(Interval(start, end))
        start = end
    return tuple(result)
