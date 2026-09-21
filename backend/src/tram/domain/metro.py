"""Types for the separate quarterly metro experiment, not the tram API time grid."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from tram.domain.errors import DomainError
from tram.domain.time import MOSCOW


@dataclass(frozen=True, order=True)
class Quarter:
    year: int
    number: int

    def __post_init__(self):
        if type(self.year) is not int or not 1900 <= self.year <= 2100:
            raise DomainError("Quarter year must be an integer in 1900..2100")
        if type(self.number) is not int or not 1 <= self.number <= 4:
            raise DomainError("Quarter number must be an integer in 1..4")

    @classmethod
    def parse(cls, value: str):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-Q[1-4]", value):
            raise DomainError("Expected YYYY-Q1..Q4")
        return cls(int(value[:4]), int(value[-1]))

    @property
    def ordinal(self):
        return self.year * 4 + self.number - 1

    @property
    def start(self):
        return datetime(self.year, 3 * self.number - 2, 1, tzinfo=MOSCOW)

    def shift(self, count: int):
        year, index = divmod(self.ordinal + count, 4)
        return Quarter(year, index + 1)

    def __str__(self):
        return f"{self.year:04d}-Q{self.number}"


def quarter_grid(start: Quarter, end: Quarter):
    """Half-open quarter range."""
    return tuple(start.shift(n) for n in range(end.ordinal - start.ordinal))


def series_identity(station: str, line: str):
    """Stable for an exact source label pair; never a claim of physical identity."""
    key = json.dumps([station, line], ensure_ascii=False, separators=(",", ":"))
    namespace = uuid5(NAMESPACE_URL, "https://data.mos.ru/opendata/62743#series-v1")
    return "metro-" + str(uuid5(namespace, key))


@dataclass(frozen=True)
class MetroEntrance:
    source_id: int
    name: str
    station: str
    line: str
    longitude: float
    latitude: float
    status: str
    in_moscow: bool


@dataclass(frozen=True)
class MetroFlow:
    source_id: int
    station: str
    line: str
    quarter: Quarter
    incoming: int
    outgoing: int


@dataclass(frozen=True)
class QuarterlyPoint:
    series_id: str
    quarter: Quarter
    incoming: int | None
    outgoing: int | None
    missing_reason: str | None = None

    def __post_init__(self):
        if not isinstance(self.series_id, str) or not self.series_id:
            raise DomainError("A series ID is required")
        for value in (self.incoming, self.outgoing):
            if value is not None and (type(value) is not int or value < 0):
                raise DomainError("Passenger counts must be nonnegative integers or null")
        if (self.incoming is None) != (self.outgoing is None):
            raise DomainError("A source row must have both metrics or be explicitly missing")
        if (self.incoming is None) != (self.missing_reason is not None):
            raise DomainError("Missing rows require a reason; observed zeros are not missing")


@dataclass(frozen=True)
class QuarterSplit:
    train_start: Quarter
    validation_start: Quarter
    test_start: Quarter
    test_end: Quarter

    def __post_init__(self):
        if not self.train_start < self.validation_start < self.test_start < self.test_end:
            raise DomainError("Train, validation and test must be ordered and nonempty")
        if self.validation_start.ordinal - self.train_start.ordinal < 4:
            raise DomainError("At least four training quarters are required for the baseline")

    def partition(self, quarter: Quarter):
        if self.train_start <= quarter < self.validation_start:
            return "train"
        if self.validation_start <= quarter < self.test_start:
            return "validation"
        if self.test_start <= quarter < self.test_end:
            return "test"
        return None
