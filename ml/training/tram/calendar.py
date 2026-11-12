"""Russian production calendar for the model features.

The table production_calendar_ru.csv comes from scripts/fetch_production_calendar.py
(isdayoff.ru, built from the Government decrees on transferred days off). For each date it
says whether the day is off and whether it is a shortened pre-holiday working day.

A day off counts as a holiday when its run of consecutive days off contains an official
public holiday (Labour Code, art. 112) or a weekday off (a transferred day). So the weekend
next to 23 February or inside the New Year break is a holiday, an ordinary weekend is not.
Dates outside the table fall back to weekends plus the art. 112 holidays (transfers of days
off are unknown there); calendar_covers() lets callers check coverage first.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from functools import cache
from pathlib import Path

import pandas as pd

CALENDAR_FILE = Path(__file__).with_name("production_calendar_ru.csv")

# Official non-working public holidays, Labour Code of the Russian Federation, art. 112.
PUBLIC_HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
    [(1, day) for day in range(1, 9)] + [(2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4)]
)


@cache
def _table() -> dict[date, tuple[bool, bool]]:
    with CALENDAR_FILE.open(encoding="utf-8") as stream:
        return {
            date.fromisoformat(row["date"]): (row["day_off"] == "1", row["short_day"] == "1")
            for row in csv.DictReader(stream)
        }


def calendar_covers(days) -> bool:
    """True if every given date is in the production calendar table."""
    table = _table()
    return all(pd.Timestamp(day).date() in table for day in days)


def _day_off(day: date) -> bool:
    known = _table().get(day)
    if known:
        return known[0]
    # Outside the table the law still fixes the holidays; only transfers are unknown.
    return day.weekday() >= 5 or (day.month, day.day) in PUBLIC_HOLIDAYS


@cache
def day_info(day: date) -> tuple[int, int, int]:
    """(is_holiday, is_short_day, is_working_weekend) for one date."""
    table = _table()
    known = table.get(day)
    off = _day_off(day)
    short = int(bool(known and known[1]))
    working_weekend = int(day.weekday() >= 5 and not off)
    if not off:
        return 0, short, working_weekend
    # Walk the run of consecutive days off around this day.
    start = day
    while _day_off(start - timedelta(days=1)):
        start -= timedelta(days=1)
    end = day
    while _day_off(end + timedelta(days=1)):
        end += timedelta(days=1)
    current, holiday = start, False
    while current <= end:
        if (current.month, current.day) in PUBLIC_HOLIDAYS or (
            current.weekday() < 5 and current in table
        ):
            holiday = True
            break
        current += timedelta(days=1)
    return int(holiday), short, working_weekend


def day_flags(dates: pd.Series) -> pd.DataFrame:
    """Holiday, short-day and working-weekend flags for a column of dates."""
    unique = pd.to_datetime(dates.drop_duplicates())
    info = {stamp.strftime("%Y-%m-%d"): day_info(stamp.date()) for stamp in unique}
    keys = pd.to_datetime(dates).dt.strftime("%Y-%m-%d")
    flags = pd.DataFrame(
        [info[key] for key in keys],
        columns=["is_holiday", "is_preholiday", "is_working_weekend"],
        index=dates.index,
    )
    return flags
