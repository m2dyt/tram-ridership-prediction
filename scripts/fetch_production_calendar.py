"""Download the official Russian production calendar and save it for the model features.

Source: isdayoff.ru, a public API built from the Government decrees on transferred days off.
For every date it returns 0 (working day), 1 (day off) or 2 (shortened pre-holiday day).

Output (committed to the repository, read by ml/training/tram/calendar.py):
1. ml/training/tram/production_calendar_ru.csv  with columns date, day_off, short_day
2. ml/training/tram/production_calendar_ru.meta.json  with source URLs, retrieval time and SHA-256

Run again when the Government publishes the decree for the next year:
    python scripts/fetch_production_calendar.py --years 2024 2025 2026 2027
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "ml" / "training" / "tram"
URL = "https://isdayoff.ru/api/getdata?year={year}&pre=1"


def fetch_year(year: int, attempts: int = 4) -> str:
    request = urllib.request.Request(
        URL.format(year=year), headers={"User-Agent": "tram-ridership-prediction/1.0"}
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                codes = response.read().decode("ascii").strip()
            break
        except OSError:
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)
    days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
    if len(codes) != days or set(codes) - {"0", "1", "2"}:
        raise ValueError(f"Unexpected answer for {year}: {len(codes)} codes, expected {days}")
    return codes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="+", default=[2024, 2025, 2026, 2027])
    args = parser.parse_args()

    rows, sources = ["date,day_off,short_day"], []
    for year in sorted(args.years):
        codes = fetch_year(year)
        sources.append(
            {
                "year": year,
                "url": URL.format(year=year),
                "sha256": hashlib.sha256(codes.encode()).hexdigest(),
            }
        )
        day = date(year, 1, 1)
        for code in codes:
            rows.append(f"{day.isoformat()},{int(code == '1')},{int(code == '2')}")
            day += timedelta(days=1)

    csv_path = OUT_DIR / "production_calendar_ru.csv"
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    meta = {
        "provider": "isdayoff.ru",
        "basis": "Постановления Правительства РФ о переносе выходных дней",
        "retrieved_at": datetime.now(UTC).isoformat(),
        "years": sorted(args.years),
        "sources": sources,
        "file_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }
    (OUT_DIR / "production_calendar_ru.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved {len(rows) - 1} days to {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
