"""Import an explicit GeoJSON export; no guessed Moscow catalogue IDs or field meanings."""

import hashlib
from pathlib import Path
from urllib.parse import urlparse

from tram.infrastructure.contract import strict_json
from tram.infrastructure.sources import coordinates


def read_geojson(path, source_url, category, id_field, name_field):
    if urlparse(source_url).hostname != "data.mos.ru":
        raise ValueError("Use the exact data.mos.ru dataset page as provenance")
    path = Path(path)
    if path.stat().st_size > 50_000_000:
        raise ValueError("Export exceeds 50 MB; split it first")
    raw = path.read_bytes()
    data = strict_json(raw)
    if data.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection")
    if data.get("crs") is not None:
        raise ValueError("Use RFC7946 WGS84 GeoJSON without a legacy crs member")
    rows, seen = [], set()
    for feature in data["features"]:
        props, geometry = feature["properties"], feature["geometry"]
        if geometry is None or geometry["type"] != "Point":
            raise ValueError("Only explicit WGS84 Point features are supported")
        point = coordinates(*geometry["coordinates"][:2])
        identity = str(props[id_field])
        if identity in seen or point is None:
            raise ValueError("Duplicate feature ID or missing coordinates")
        seen.add(identity)
        rows.append(
            {
                "id": identity,
                "title": str(props[name_field]),
                "coordinates": point,
                "category": category,
            }
        )
    return {
        "status": "succeeded",
        "kind": "geo",
        "records": rows,
        "record_count": len(rows),
        "warnings": [
            "Imported file; verify source terms and coordinate reference system",
            "sha256:" + hashlib.sha256(raw).hexdigest(),
        ],
        "attribution": "Портал открытых данных Москвы",
        "source_url": source_url,
    }
