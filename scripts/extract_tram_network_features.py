"""Extract spatial, operational, and track segregation features for Moscow tram routes from raw sources.

Produces:
1. data/tram_route_features.csv - route-level tabular features for ML models.
2. data/tram_stops_wgs84.csv - normalized tram stops registry with coordinates.
3. data/tram_network.geojson - GeoJSON FeatureCollection for backend and map frontend.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

MOSCOW_CENTER_LAT = 55.751244
MOSCOW_CENTER_LON = 37.618423

TARGET_ROUTES: list[int] = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]

METRO_KEYWORDS: list[str] = [
    "м.",
    "метро",
    "мцк",
    "мцд",
    "вокзал",
    "станция метро",
]


def haversine_distance_km(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Calculate the great circle distance between two points on the earth in km."""
    r = 6371.0  # Earth's radius in kilometers
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta_phi = np.radians(lat2 - lat1)
    delta_lambda = np.radians(lon2 - lon1)

    a = np.sin(delta_phi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return r * c


def point_to_segment_dist_m(plat: float, plon: float, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate orthogonal distance from point to segment in meters."""
    dx = (lon2 - lon1) * 62392.0
    dy = (lat2 - lat1) * 111139.0
    dpx = (plon - lon1) * 62392.0
    dpy = (plat - lat1) * 111139.0

    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0.0:
        return float(np.sqrt(dpx * dpx + dpy * dpy))

    t = max(0.0, min(1.0, (dpx * dx + dpy * dy) / seg_len_sq))
    proj_x = dx * t
    proj_y = dy * t
    return float(np.sqrt((dpx - proj_x) ** 2 + (dpy - proj_y) ** 2))


def extract_features(
    stops_path: Path,
    actual_path: Path,
    output_dir: Path,
    tramlanes_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading stops from {stops_path}...")
    stops_df = pd.read_csv(stops_path, encoding="utf-8")
    trams_stops = stops_df[stops_df["transport_type"] == "tram"].copy()

    print(f"Loading telemetry from {actual_path}...")
    actual_df = pd.read_csv(actual_path, encoding="utf-8")
    trams_actual = actual_df[actual_df["transport_type"] == "tram"].copy()

    # Load tramlanes if available
    moscow_segments: list[tuple[float, float, float, float, str]] = []
    if tramlanes_path and tramlanes_path.is_file():
        print(f"Loading tram track segregation from {tramlanes_path}...")
        with open(tramlanes_path, encoding="utf-8") as f:
            lanes_data = json.load(f)
        for feat in lanes_data.get("features", []):
            if "москва" in str(feat.get("properties", {}).get("name", "")).lower():
                t = feat.get("properties", {}).get("type", "Обособленные")
                coords = feat.get("geometry", {}).get("coordinates", [])
                for i in range(len(coords) - 1):
                    lon1, lat1 = coords[i]
                    lon2, lat2 = coords[i + 1]
                    moscow_segments.append((lat1, lon1, lat2, lon2, t))
        print(f"Loaded {len(moscow_segments)} Moscow track segments.")

    # Route-level features collection
    route_metrics: list[dict] = []
    clean_stops_list: list[pd.DataFrame] = []
    geojson_features: list[dict] = []

    for route in TARGET_ROUTES:
        r_str = str(route)
        r_stops = trams_stops[trams_stops["number"] == r_str].copy()
        r_actual = trams_actual[trams_actual["number"] == r_str].copy()

        # Handle inactive / fictitious routes (Route 5)
        if len(r_stops) == 0:
            print(f"Route {route}: inactive / no stop data found (filling zeros).")
            route_metrics.append(
                {
                    "route": route,
                    "route_is_active": 0,
                    "route_num_stops": 0,
                    "route_length_km": 0.0,
                    "route_metro_stops": 0,
                    "route_metro_ratio": 0.0,
                    "route_center_dist_km": 0.0,
                    "route_mean_delay_min": 0.0,
                    "route_late_ratio": 0.0,
                    "route_punctuality_ratio": 0.0,
                    "route_delay_std": 0.0,
                    "route_fleet_proxy": 0,
                    "route_segregated_ratio": 0.0,
                    "route_shared_stops": 0,
                }
            )
            continue

        # Clean stops
        unique_stops = r_stops.drop_duplicates(subset=["stop_id"]).copy()
        num_stops = len(unique_stops)
        unique_stops["route"] = route
        clean_stops_list.append(unique_stops[["route", "stop_id", "name", "last_stop_name", "lon", "lat"]])

        # Metro connectivity
        name_lower = unique_stops["name"].fillna("").str.lower()
        is_metro = name_lower.apply(lambda s: any(kw in s for kw in METRO_KEYWORDS))
        metro_stops = int(is_metro.sum())
        metro_ratio = round(metro_stops / max(1, num_stops), 4)

        # Centroid and distance to Moscow center
        mean_lat = float(unique_stops["lat"].mean())
        mean_lon = float(unique_stops["lon"].mean())
        dist_to_center = float(haversine_distance_km(mean_lat, mean_lon, MOSCOW_CENTER_LAT, MOSCOW_CENTER_LON))

        # Order stops and calculate route length
        ordered_coords = r_stops.drop_duplicates(subset=["lat", "lon"])[["lat", "lon"]].values
        if len(ordered_coords) > 1:
            lats1, lons1 = ordered_coords[:-1, 0], ordered_coords[:-1, 1]
            lats2, lons2 = ordered_coords[1:, 0], ordered_coords[1:, 1]
            seg_dists = haversine_distance_km(lats1, lons1, lats2, lons2)
            length_km = float(np.sum(seg_dists))
        else:
            length_km = 0.0

        # Telemetry delay metrics
        if len(r_actual) > 0:
            delay_min = (r_actual["arrival_time"] - r_actual["forecast_time"]) / 60.0
            valid_delay = delay_min.clip(-30.0, 60.0)
            mean_delay = float(valid_delay.mean())
            delay_std = float(valid_delay.std())
            late_ratio = float((valid_delay > 1.0).mean() * 100.0)
            punctuality_ratio = float(100.0 - late_ratio)
            fleet_proxy = int(r_actual["tmId"].nunique())
        else:
            mean_delay, delay_std, late_ratio, punctuality_ratio, fleet_proxy = (
                0.0,
                0.0,
                0.0,
                0.0,
                0,
            )

        # Track segregation calculation from tramlanes
        segregated_stops = 0
        shared_stops = 0
        if moscow_segments:
            for _, s_row in unique_stops.iterrows():
                slat, slon = float(s_row["lat"]), float(s_row["lon"])
                min_d = 999999.0
                best_t = "Обособленные"
                for lat1, lon1, lat2, lon2, t in moscow_segments:
                    if abs(slat - (lat1 + lat2) / 2) > 0.003 or abs(slon - (lon1 + lon2) / 2) > 0.005:
                        continue
                    d = point_to_segment_dist_m(slat, slon, lat1, lon1, lat2, lon2)
                    if d < min_d:
                        min_d = d
                        best_t = t
                if min_d <= 100.0:
                    if best_t == "Обособленные":
                        segregated_stops += 1
                    else:
                        shared_stops += 1
                else:
                    segregated_stops += 1

        tot_matched = segregated_stops + shared_stops
        segregated_ratio = round(segregated_stops / max(1, tot_matched), 4) if tot_matched > 0 else 1.0

        route_metrics.append(
            {
                "route": route,
                "route_is_active": 1,
                "route_num_stops": num_stops,
                "route_length_km": round(length_km, 2),
                "route_metro_stops": metro_stops,
                "route_metro_ratio": metro_ratio,
                "route_center_dist_km": round(dist_to_center, 2),
                "route_mean_delay_min": round(mean_delay, 2),
                "route_late_ratio": round(late_ratio, 2),
                "route_punctuality_ratio": round(punctuality_ratio, 2),
                "route_delay_std": round(delay_std, 2),
                "route_fleet_proxy": fleet_proxy,
                "route_segregated_ratio": segregated_ratio,
                "route_shared_stops": shared_stops,
            }
        )

        # GeoJSON LineString for route
        line_coords = [[float(lon), float(lat)] for lat, lon in ordered_coords]
        geojson_features.append(
            {
                "type": "Feature",
                "properties": {
                    "route": route,
                    "name": f"Трамвай {route}",
                    "num_stops": num_stops,
                    "length_km": round(length_km, 2),
                    "metro_stops": metro_stops,
                    "late_ratio": round(late_ratio, 2),
                    "segregated_ratio": segregated_ratio,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": line_coords,
                },
            }
        )

        # GeoJSON Points for stops
        for _, stop_row in unique_stops.iterrows():
            geojson_features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "route": route,
                        "stop_id": str(stop_row["stop_id"]),
                        "name": str(stop_row["name"]),
                        "last_stop_name": str(stop_row["last_stop_name"]),
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(stop_row["lon"]), float(stop_row["lat"])],
                    },
                }
            )

    # DataFrames assembly
    df_features = pd.DataFrame(route_metrics)
    df_stops = pd.concat(clean_stops_list, ignore_index=True) if clean_stops_list else pd.DataFrame()
    geojson_data = {
        "type": "FeatureCollection",
        "features": geojson_features,
    }

    # Save to data directory
    out_features_path = output_dir / "tram_route_features.csv"
    out_stops_path = output_dir / "tram_stops_wgs84.csv"
    out_geojson_path = output_dir / "tram_network.geojson"

    df_features.to_csv(out_features_path, index=False)
    df_stops.to_csv(out_stops_path, index=False)
    with open(out_geojson_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)

    print("\nSuccessfully generated:")
    print(f"1. {out_features_path} ({len(df_features)} routes)")
    print(f"2. {out_stops_path} ({len(df_stops)} stops)")
    print(f"3. {out_geojson_path} ({len(geojson_features)} features)")

    return df_features, df_stops, geojson_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract spatial, operational, and track segregation tram features.")
    parser.add_argument(
        "--stops-path",
        type=Path,
        default=Path("sources/moscow-public-transport/stop_from_repo.csv"),
        help="Path to stops CSV file.",
    )
    parser.add_argument(
        "--actual-path",
        type=Path,
        default=Path("sources/moscow-public-transport/actual_vs_forecasted.csv"),
        help="Path to telemetry CSV file.",
    )
    parser.add_argument(
        "--tramlanes-path",
        type=Path,
        default=Path("tramlanes.geojson"),
        help="Path to tramlanes.geojson file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Output directory for generated datasets.",
    )

    args = parser.parse_args()
    extract_features(args.stops_path, args.actual_path, args.output_dir, tramlanes_path=args.tramlanes_path)


if __name__ == "__main__":
    main()
