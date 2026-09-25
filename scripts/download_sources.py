"""Download, import, and generate provenance for external datasets.

Supported sources:
1. data.mos.ru (624: Metro entrances, 62743: Metro ridership flow):
   - Import from downloaded browser export ZIP/JSON or fetch via API with key.
   - Generates provenance.json required by `prepare-metro`.
2. Open-Meteo: Historical hourly weather for Moscow.
3. KudaGo: Public events API for Moscow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = ROOT / "sources"


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def fetch_url(url: str, dest_path: Path, headers: dict[str, str] | None = None) -> str:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "TramRidership/1.0"})
    print(f"Fetching: {url}")
    with urllib.request.urlopen(req, timeout=60) as resp, dest_path.open("wb") as out:
        while chunk := resp.read(65536):
            out.write(chunk)
    digest = sha256_file(dest_path)
    print(f"Saved: {dest_path} ({dest_path.stat().st_size} bytes, sha256: {digest[:8]}...)")
    return digest


def cmd_import_mos(args: argparse.Namespace) -> int:
    """Import a downloaded ZIP or JSON from data.mos.ru and generate valid provenance.json."""
    source_file = Path(args.file).resolve()
    if not source_file.is_file():
        print(f"Error: file not found: {source_file}", file=sys.stderr)
        return 1

    dataset_id = str(args.dataset)
    if dataset_id not in ("624", "62743"):
        print(f"Warning: Unexpected dataset ID '{dataset_id}', expected '624' or '62743'", file=sys.stderr)

    date_str = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    target_dir = SOURCES_DIR / "data-mos" / dataset_id / date_str
    target_dir.mkdir(parents=True, exist_ok=True)

    extracted_data_file: Path | None = None
    artifacts: list[dict[str, str]] = []

    # If it's a zip archive
    if zipfile.is_zipfile(source_file):
        dest_zip = target_dir / source_file.name
        if source_file != dest_zip:
            dest_zip.write_bytes(source_file.read_bytes())
        artifacts.append({"file": dest_zip.name, "sha256": sha256_file(dest_zip)})

        with zipfile.ZipFile(dest_zip, "r") as zf:
            for member in zf.namelist():
                if member.endswith(".json") and ("data-" in member or "data_" in member or member.startswith("data")):
                    extracted_path = target_dir / Path(member).name
                    extracted_path.write_bytes(zf.read(member))
                    extracted_data_file = extracted_path
                    artifacts.append({"file": extracted_path.name, "sha256": sha256_file(extracted_path)})
                elif member.endswith(".json"):
                    extracted_path = target_dir / Path(member).name
                    extracted_path.write_bytes(zf.read(member))
                    artifacts.append({"file": extracted_path.name, "sha256": sha256_file(extracted_path)})
    else:
        # Single JSON file
        dest_file = target_dir / source_file.name
        if source_file != dest_file:
            dest_file.write_bytes(source_file.read_bytes())
        extracted_data_file = dest_file
        artifacts.append({"file": dest_file.name, "sha256": sha256_file(dest_file)})

    if not extracted_data_file:
        # Search for any json file in target_dir
        json_files = list(target_dir.glob("data-*.json")) or list(target_dir.glob("*.json"))
        if json_files:
            extracted_data_file = json_files[0]
        else:
            print("Error: Could not find extracted data JSON file", file=sys.stderr)
            return 1

    retrieved_at = datetime.now(UTC).isoformat()
    version = args.version or ("6.8" if dataset_id == "624" else "1.35")

    provenance = {
        "provider": "data.mos.ru",
        "dataset_id": dataset_id,
        "source_url": f"https://data.mos.ru/opendata/{dataset_id}",
        "source_version": version,
        "retrieved_at": retrieved_at,
        "artifacts": artifacts,
    }

    prov_path = target_dir / "provenance.json"
    prov_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Successfully imported dataset {dataset_id} into {target_dir}")
    print(f"Primary data file: {extracted_data_file.name}")
    print(f"Created provenance: {prov_path}")
    return 0


def cmd_weather(args: argparse.Namespace) -> int:
    """Download historical weather from Open-Meteo Archive API."""
    date_dir = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    target_dir = SOURCES_DIR / "open-meteo" / date_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    start_date = args.start_date
    end_date = args.end_date
    lat = args.latitude
    lon = args.longitude

    url = (
        f"https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat}&longitude={lon}&start_date={start_date}&end_date={end_date}&"
        f"hourly=temperature_2m,precipitation,wind_speed_10m&timezone=UTC"
    )

    filename = f"moscow-{start_date}_{end_date}.json"
    out_file = target_dir / filename

    try:
        digest = fetch_url(url, out_file)
    except Exception as e:
        print(f"Error fetching Open-Meteo data: {e}", file=sys.stderr)
        return 1

    retrieved_at = datetime.now(UTC).isoformat()
    provenance = {
        "provider": "open-meteo.com",
        "dataset_id": "historical-weather",
        "source_url": url,
        "source_version": "v1",
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "raw_file": filename,
        "artifacts": [{"file": filename, "sha256": digest}],
        "license_url": "https://open-meteo.com/en/terms",
        "attribution": "Weather data by Open-Meteo.com under CC BY 4.0",
    }

    prov_path = target_dir / "provenance.json"
    prov_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved weather dataset and provenance to {target_dir}")
    return 0


def cmd_kudago(args: argparse.Namespace) -> int:
    """Download events from KudaGo API."""
    date_dir = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    target_dir = SOURCES_DIR / "kudago" / date_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    page_size = args.page_size
    url = (
        f"https://kudago.com/public-api/v1.4/events/?"
        f"location=msk&page_size={page_size}&fields=id,title,dates,place,site_url&expand=place"
    )

    filename = "moscow-events-page-1.json"
    out_file = target_dir / filename

    try:
        digest = fetch_url(url, out_file)
    except Exception as e:
        print(f"Error fetching KudaGo events: {e}", file=sys.stderr)
        return 1

    retrieved_at = datetime.now(UTC).isoformat()
    provenance = {
        "provider": "kudago.com",
        "dataset_id": "events-msk",
        "source_url": url,
        "source_version": "v1.4",
        "retrieved_at": retrieved_at,
        "content_sha256": digest,
        "raw_file": filename,
        "artifacts": [{"file": filename, "sha256": digest}],
        "attribution": "Events data by KudaGo API",
    }

    prov_path = target_dir / "provenance.json"
    prov_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved KudaGo events sample and provenance to {target_dir}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify all provenance.json files and artifact checksums in sources/."""
    provenance_files = list(SOURCES_DIR.glob("**/provenance.json"))
    if not provenance_files:
        print(f"No provenance.json files found in {SOURCES_DIR}")
        return 0

    print(f"Found {len(provenance_files)} provenance files to verify.")
    all_ok = True
    for prov_path in provenance_files:
        try:
            data = json.loads(prov_path.read_text(encoding="utf-8"))
            artifacts = data.get("artifacts", [])
            for art in artifacts:
                art_file = prov_path.parent / art["file"]
                if not art_file.exists():
                    print(f"FAIL: Missing artifact {art_file}")
                    all_ok = False
                    continue
                actual_sha = sha256_file(art_file)
                if actual_sha != art["sha256"]:
                    print(f"FAIL: SHA-256 mismatch in {art_file}: expected {art['sha256']}, got {actual_sha}")
                    all_ok = False
                else:
                    print(f"OK: {art_file.relative_to(ROOT)} (SHA-256 matches)")
        except Exception as e:
            print(f"Error parsing {prov_path}: {e}")
            all_ok = False

    return 0 if all_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and prepare external datasets")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # import-mos
    p_mos = subparsers.add_parser("import-mos", help="Import downloaded 624/62743 ZIP/JSON and create provenance.json")
    p_mos.add_argument("--dataset", required=True, choices=["624", "62743"], help="Dataset ID (624 or 62743)")
    p_mos.add_argument("--file", required=True, help="Path to downloaded ZIP or JSON file")
    p_mos.add_argument("--version", help="Source version string (e.g. '6.8' or '1.35')")
    p_mos.add_argument("--date", help="Folder date (YYYY-MM-DD), defaults to today")

    # weather
    p_weather = subparsers.add_parser("weather", help="Download Open-Meteo historical weather")
    p_weather.add_argument("--start-date", default="2025-01-01", help="Start date (YYYY-MM-DD)")
    p_weather.add_argument("--end-date", default="2025-01-07", help="End date (YYYY-MM-DD)")
    p_weather.add_argument("--latitude", default="55.75", help="Latitude")
    p_weather.add_argument("--longitude", default="37.62", help="Longitude")
    p_weather.add_argument("--date", help="Folder date (YYYY-MM-DD), defaults to today")

    # kudago
    p_kudago = subparsers.add_parser("kudago", help="Download KudaGo Moscow events sample")
    p_kudago.add_argument("--page-size", default=10, type=int, help="Number of events to retrieve")
    p_kudago.add_argument("--date", help="Folder date (YYYY-MM-DD), defaults to today")

    # verify
    subparsers.add_parser("verify", help="Verify provenance and hashes in sources/")

    args = parser.parse_args()
    if args.command == "import-mos":
        return cmd_import_mos(args)
    if args.command == "weather":
        return cmd_weather(args)
    if args.command == "kudago":
        return cmd_kudago(args)
    if args.command == "verify":
        return cmd_verify(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
