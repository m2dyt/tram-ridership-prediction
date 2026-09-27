import json
import csv
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

from tram.infrastructure.contract import Contract
from tram.infrastructure.bundles import read_bundle

MOSCOW = ZoneInfo("Europe/Moscow")

def build_bundle(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Load routes & stops
    with open('frontend/public/moscow_tram_routes.json', 'r', encoding='utf-8') as f:
        routes_geo = json.load(f)
    with open('frontend/public/moscow_tram_stops.json', 'r', encoding='utf-8') as f:
        stops_geo = json.load(f)

    # 10 hackathon routes
    route_nums = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]
    route_ids = [f"hackathon-{n}" for n in route_nums]

    # Shared stops dictionary across all routes to prevent conflicting shared stops
    global_stops = {}

    network_routes = []
    for num in route_nums:
        r_id = f"hackathon-{num}"
        stops_list = stops_geo.get(str(num), [])
        
        # If no stops in json, provide fallback stops
        if not stops_list:
            stops_list = [
                {"id": f"stop-{num}-01", "name": f"Остановка 1 (маршрут {num})", "geometry": {"type": "Point", "coordinates": [37.62, 55.75]}},
                {"id": f"stop-{num}-02", "name": f"Остановка 2 (маршрут {num})", "geometry": {"type": "Point", "coordinates": [37.63, 55.76]}}
            ]
        
        route_stops = []
        for i, s in enumerate(stops_list):
            s_id = s.get("id") or f"stop-{num}-{i+1}"
            stop_obj = {
                "id": s_id,
                "name": s.get("name") or f"Остановка {i+1}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        float(s["geometry"]["coordinates"][0]),
                        float(s["geometry"]["coordinates"][1])
                    ]
                }
            }
            # Ensure consistent definition if shared
            if s_id in global_stops:
                stop_obj = global_stops[s_id]
            else:
                global_stops[s_id] = stop_obj
            route_stops.append(stop_obj)

        # Build directions and segments
        direction_stops = []
        segments = []
        for idx, s in enumerate(route_stops):
            direction_stops.append({"stop_id": s["id"], "sequence": idx + 1})
            if idx > 0:
                prev_s = route_stops[idx - 1]
                segments.append({
                    "id": f"seg-{r_id}-{idx}",
                    "from_stop_id": prev_s["id"],
                    "from_sequence": idx,
                    "to_stop_id": s["id"],
                    "to_sequence": idx + 1,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            prev_s["geometry"]["coordinates"],
                            s["geometry"]["coordinates"]
                        ]
                    }
                })

        directions = [
            {
                "id": f"dir-{r_id}-direct",
                "name": f"Прямое направление № {num}",
                "stops": direction_stops,
                "segments": segments,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [s["geometry"]["coordinates"] for s in route_stops]
                }
            }
        ]

        network_routes.append({
            "network_revision_id": "competition-network-v1",
            "valid_at": "2025-01-01",
            "route": {
                "id": r_id,
                "number": str(num),
                "name": f"Трамвай № {num} (Москва)",
                "valid_from": "2025-01-01",
                "valid_to": None
            },
            "stops": route_stops,
            "warnings": [],
            "directions": directions
        })

    # Date range for observations: 2025-01-01 to 2025-10-31 (304 days)
    start_dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=MOSCOW)
    end_dt = datetime(2025, 11, 1, 0, 0, 0, tzinfo=MOSCOW) # up to Nov 1

    profile_id = "competition-boardings-route-day"
    forecast_profile_id = "competition-forecast-month"

    manifest = {
        "capabilities": {
            "dataset_revision_id": "competition-data-v1",
            "network_revision_id": "competition-network-v1",
            "source_mode": "batch",
            "timezone": "Europe/Moscow",
            "observation_profiles": [
                {
                    "id": profile_id,
                    "metric": "boardings",
                    "unit": "passengers",
                    "spatial_level": "route",
                    "resolution": "day",
                    "route_ids": route_ids,
                    "history_start": start_dt.isoformat(),
                    "history_end": end_dt.isoformat(),
                    "aggregation_method": "sum",
                    "limitations": [
                        "Official Moscow Tram Competition dataset (train + test splits)"
                    ]
                }
            ],
            "forecast_profiles": [
                {
                    "id": forecast_profile_id,
                    "metric": "boardings",
                    "unit": "passengers",
                    "spatial_level": "route",
                    "resolution": "day",
                    "route_ids": route_ids,
                    "aggregation_method": "sum",
                    "observation_profile_id": profile_id,
                    "horizon": "month",
                    "availability": "available",
                    "unavailable_reason": None,
                    "allowed_as_of_start": "2025-10-31T00:00:00+03:00",
                    "allowed_as_of_end": "2025-10-31T00:00:00+03:00",
                    "forecast_start_min": "2025-11-01T00:00:00+03:00",
                    "forecast_start_max": "2025-11-01T00:00:00+03:00",
                    "start_alignment": "local_midnight",
                    "evaluation_status": "pending",
                    "prediction_interval_available": False,
                    "limitations": [
                        "CatBoost inference & seasonal benchmark"
                    ]
                }
            ],
            "max_page_size": 1000,
            "max_routes_per_run": 100,
            "warnings": []
        },
        "network": {
            "id": "competition-network-v1",
            "routes": network_routes
        },
        "sources": [
            {
                "source": "validations",
                "source_mode": "batch",
                "event_watermark": "2025-10-31T23:59:59+03:00",
                "ingested_at": "2025-10-31T23:59:59+03:00",
                "freshness": "fresh",
                "stale_after_seconds": None,
                "quality": {
                    "status": "unverified",
                    "coverage_ratio": None,
                    "flags": [
                        "competition_dataset"
                    ]
                }
            }
        ],
        "models": [
            {
                "profile_ids": [forecast_profile_id],
                "model": {
                    "id": "seasonal-baseline-day",
                    "version": "1",
                    "method": "seasonal_naive_v1",
                    "is_baseline": True,
                    "feature_set_version": "calendar_v1",
                    "training_history_end": "2025-10-31T00:00:00+03:00"
                }
            }
        ],
        "series": [
            {
                "profile_id": profile_id,
                "spatial": {
                    "level": "route",
                    "route_id": r_id,
                    "direction_id": None,
                    "stop_id": None,
                    "stop_sequence": None,
                    "segment_id": None
                },
                "geometry": None,
                "coverage_start": start_dt.isoformat(),
                "coverage_end": end_dt.isoformat()
            }
            for r_id in route_ids
        ]
    }

    # 2. Load observations from labels_day_train.csv and labels_day_test.csv
    df_train = pd.read_csv('data/labels/labels_day_train.csv', sep=';')
    df_test = pd.read_csv('data/labels/labels_day_test.csv', sep=';')
    df_all = pd.concat([df_train, df_test], ignore_index=True)

    # Group by route and date, sum boardings
    df_daily = df_all.groupby(['route', 'date'])['boardings'].sum().reset_index()
    daily_map = {}
    for _, row in df_daily.iterrows():
        daily_map[(int(row['route']), str(row['date']))] = float(row['boardings'])

    # Write observations.jsonl
    # Grid of dates from 2025-01-01 to 2025-10-31 (every day must be strictly sequential!)
    current = start_dt
    days_list = []
    while current < end_dt:
        nxt = current + timedelta(days=1)
        days_list.append((current, nxt, current.strftime("%Y-%m-%d")))
        current = nxt

    now_iso = datetime.now(MOSCOW).isoformat()

    obs_count = 0
    with open(output_dir / "observations.jsonl", "w", encoding="utf-8") as f_out:
        for num in route_nums:
            r_id = f"hackathon-{num}"
            for c_start, c_end, d_str in days_list:
                # Value for route
                val = daily_map.get((num, d_str), 0.0)
                available_at = (c_end + timedelta(hours=3)).isoformat()
                if parse_time_obj(available_at) > datetime.now(MOSCOW):
                    available_at = now_iso

                record = {
                    "profile_id": profile_id,
                    "available_at": available_at,
                    "point": {
                        "spatial": {
                            "level": "route",
                            "route_id": r_id,
                            "direction_id": None,
                            "stop_id": None,
                            "stop_sequence": None,
                            "segment_id": None
                        },
                        "interval_start": c_start.isoformat(),
                        "interval_end": c_end.isoformat(),
                        "value": val,
                        "value_kind": "observed",
                        "estimation_method": None,
                        "missing_reason": None,
                        "quality": {
                            "status": "ok",
                            "coverage_ratio": 1.0,
                            "flags": []
                        }
                    }
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                obs_count += 1

    # Save manifest.json
    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated {output_dir}:")
    print(f" - Routes: {len(route_nums)}")
    print(f" - Observations: {obs_count}")
    print(f" - Date range: 2025-01-01 to 2025-10-31 ({len(days_list)} days)")

def parse_time_obj(s: str) -> datetime:
    return datetime.fromisoformat(s)

if __name__ == "__main__":
    out = Path("data/competition_bundle")
    build_bundle(out)
