"""Fetch and normalize complete 2025 hourly weather data for Moscow from Open-Meteo Archive API.

Outputs:
1. Raw JSON: sources/open-meteo/2025/weather_moscow_2025.json
2. Provenance: sources/open-meteo/2025/provenance.json
3. Normalized table: data/weather_hourly_2025.csv (and .parquet if available)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
import pandas as pd

_WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = _WORKSPACE_ROOT / "sources" / "open-meteo" / "2025"
DATA_DIR = _WORKSPACE_ROOT / "data"

MOSCOW_LAT = 55.7558
MOSCOW_LON = 37.6173
START_DATE = "2025-01-01"
END_DATE = "2025-12-31"


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def fetch_weather(
    output_dir: Path = DATA_DIR,
    sources_dir: Path = SOURCES_DIR,
    force: bool = False,
) -> Path:
    sources_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_file = sources_dir / "weather_moscow_2025.json"
    normalized_csv = output_dir / "weather_hourly_2025.csv"

    url = (
        f"https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={MOSCOW_LAT}&longitude={MOSCOW_LON}&start_date={START_DATE}&end_date={END_DATE}&"
        f"hourly=temperature_2m,precipitation,snowfall,wind_speed_10m,weather_code&"
        f"timezone=Europe%2FMoscow"
    )

    if not raw_file.is_file() or force:
        print(f"Fetching 2025 weather from Open-Meteo Archive API:\n  {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "TramRidershipPrediction/1.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw_bytes = resp.read()
        raw_file.write_bytes(raw_bytes)
        print(f"Saved raw response to {raw_file} ({len(raw_bytes):,} bytes)")
    else:
        print(f"Using cached raw weather: {raw_file}")

    file_hash = sha256_file(raw_file)

    # Save provenance
    provenance = {
        "provider": "open-meteo.com",
        "dataset_id": "historical-weather-moscow-2025",
        "source_url": url,
        "source_version": "v1",
        "coordinates": {"latitude": MOSCOW_LAT, "longitude": MOSCOW_LON},
        "temporal_coverage": {"start": START_DATE, "end": END_DATE, "timezone": "Europe/Moscow"},
        "retrieved_at": datetime.now(UTC).isoformat(),
        "content_sha256": file_hash,
        "raw_file": raw_file.name,
        "artifacts": [{"file": raw_file.name, "sha256": file_hash}],
        "license_url": "https://open-meteo.com/en/terms",
        "attribution": "Weather data by Open-Meteo.com under CC BY 4.0",
    }
    prov_file = sources_dir / "provenance.json"
    prov_file.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")

    # Parse and normalize
    data = json.loads(raw_file.read_text(encoding="utf-8"))
    hourly = data["hourly"]

    times = hourly["time"]
    temps = hourly["temperature_2m"]
    precips = hourly["precipitation"]
    snows = hourly["snowfall"]
    winds = hourly["wind_speed_10m"]
    codes = hourly["weather_code"]

    records = []
    for t_str, temp, prec, snow, wind, code in zip(
        times, temps, precips, snows, winds, codes, strict=True
    ):
        # Time format: YYYY-MM-DDTHH:00
        dt_part, hr_part = t_str.split("T")
        hour_int = int(hr_part.split(":")[0])

        is_freezing = 1 if (temp is not None and temp < 0.0) else 0
        is_precipitation = 1 if (prec is not None and prec > 0.0) else 0
        # WMO Snow codes: 71, 73, 75 (slight/mod/heavy snow), 77 (snow grains), 85, 86 (snow showers)
        is_snow = 1 if ((snow is not None and snow > 0.0) or (code in [71, 73, 75, 77, 85, 86])) else 0
        is_heavy_snow = 1 if ((snow is not None and snow >= 0.5) or (code in [75, 86])) else 0

        records.append(
            {
                "date": dt_part,
                "hour": hour_int,
                "temperature_2m": temp,
                "precipitation": prec,
                "snowfall": snow,
                "wind_speed_10m": wind,
                "weather_code": code,
                "is_freezing": is_freezing,
                "is_precipitation": is_precipitation,
                "is_snow": is_snow,
                "is_heavy_snow": is_heavy_snow,
            }
        )

    df_weather = pd.DataFrame(records)
    df_weather.to_csv(normalized_csv, index=False)
    print(f"Saved normalized weather to: {normalized_csv}")
    print(f"Total rows: {len(df_weather):,} (expected 8,760 for 365 days x 24h)")
    print(f"Missing values: {df_weather.isna().sum().to_dict()}")

    # Attempt parquet export if pyarrow is installed
    try:
        parquet_file = output_dir / "weather_hourly_2025.parquet"
        df_weather.to_parquet(parquet_file, index=False)
        print(f"Saved parquet version to: {parquet_file}")
    except Exception:
        pass

    return normalized_csv


def main():
    parser = argparse.ArgumentParser(description="Download and normalize Moscow 2025 weather from Open-Meteo.")
    parser.add_argument("--force", action="store_true", help="Force redownload even if cached")
    args = parser.parse_args()

    fetch_weather(force=args.force)


if __name__ == "__main__":
    main()
