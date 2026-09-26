"""Generate official Russian production calendar 2025 based on RF Decree No. 1335.

Outputs:
1. data/calendar_2025.csv
2. data/calendar_2025.meta.json
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pandas as pd

_WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = _WORKSPACE_ROOT / "data"

# Decree 1335 official transfers and non-working days for 2025
HOLIDAYS_2025 = {
    # New Year holidays
    "2025-01-01",
    "2025-01-02",
    "2025-01-03",
    "2025-01-04",
    "2025-01-05",
    "2025-01-06",
    "2025-01-07",
    "2025-01-08",
    # Defender of Fatherland
    "2025-02-22",
    "2025-02-23",
    # International Women's Day
    "2025-03-08",
    "2025-03-09",
    # Spring and Labor + transfers (Jan 4 -> May 2)
    "2025-05-01",
    "2025-05-02",
    "2025-05-03",
    "2025-05-04",
    # Victory Day + transfer (Feb 23 -> May 8)
    "2025-05-08",
    "2025-05-09",
    "2025-05-10",
    "2025-05-11",
    # Russia Day + transfer (March 8 -> June 13)
    "2025-06-12",
    "2025-06-13",
    "2025-06-14",
    "2025-06-15",
    # Unity Day + transfer (Nov 1 workday -> Nov 3 day off)
    "2025-11-02",
    "2025-11-03",
    "2025-11-04",
    # New Year Eve + transfer (Jan 5 -> Dec 31)
    "2025-12-31",
}

PRE_HOLIDAYS_2025 = {
    "2025-03-07",
    "2025-04-30",
    "2025-06-11",
    "2025-11-01",  # Working Saturday
}

TRANSFERRED_WORKDAYS = {
    "2025-11-01",  # Saturday worked instead of Monday Nov 3
}


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_calendar_2025(output_dir: Path = DATA_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")

    records = []
    for dt in dates:
        date_str = dt.strftime("%Y-%m-%d")
        dow = dt.dayofweek
        is_weekend = 1 if dow >= 5 else 0
        is_holiday = 1 if date_str in HOLIDAYS_2025 else 0
        is_preholiday = 1 if date_str in PRE_HOLIDAYS_2025 else 0
        is_transferred_workday = 1 if date_str in TRANSFERRED_WORKDAYS else 0

        # Workday logic: regular weekday that isn't holiday, OR transferred workday (Nov 1)
        if is_transferred_workday:
            is_workday = 1
            is_day_off = 0
        else:
            is_workday = 1 if (is_weekend == 0 and is_holiday == 0) else 0
            is_day_off = 1 if (is_weekend == 1 or is_holiday == 1) else 0

        # Effective day of week for public transit:
        # Holidays use Sunday schedule (dow=6), working Saturdays use Friday schedule (dow=4)
        dow_effective = dow
        if is_holiday:
            dow_effective = 6
        elif is_transferred_workday:
            dow_effective = 4

        records.append(
            {
                "date": date_str,
                "dayofweek": dow,
                "month": dt.month,
                "day": dt.day,
                "is_weekend": is_weekend,
                "is_holiday": is_holiday,
                "is_preholiday": is_preholiday,
                "is_workday": is_workday,
                "is_day_off": is_day_off,
                "is_transferred_workday": is_transferred_workday,
                "dow_effective": dow_effective,
            }
        )

    df_cal = pd.DataFrame(records)
    csv_path = output_dir / "calendar_2025.csv"
    df_cal.to_csv(csv_path, index=False)
    print(f"Saved calendar to: {csv_path} ({len(df_cal)} days)")

    file_hash = sha256_file(csv_path)
    meta = {
        "dataset_name": "calendar_2025.csv",
        "sha256": file_hash,
        "total_days": len(df_cal),
        "total_workdays": int(df_cal["is_workday"].sum()),
        "total_days_off": int(df_cal["is_day_off"].sum()),
        "legal_basis": "Постановление Правительства РФ от 04.10.2024 № 1335 «О переносе выходных дней в 2025 году»",
        "legal_url": "http://government.ru/docs/all/155500/",
    }
    meta_path = output_dir / "calendar_2025.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved calendar metadata to: {meta_path}")

    return csv_path


def main():
    generate_calendar_2025()


if __name__ == "__main__":
    main()
