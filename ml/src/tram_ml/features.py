from dataclasses import dataclass
from datetime import datetime

from tram.domain.time import MOSCOW, aware


@dataclass(frozen=True)
class CalendarFeatures:
    hour: int
    weekday: int
    month: int
    is_weekend: bool


def calendar_features(timestamp: datetime) -> CalendarFeatures:
    local = aware(timestamp).astimezone(MOSCOW)
    return CalendarFeatures(local.hour, local.weekday(), local.month, local.weekday() >= 5)
