"""Additional CLI adapters. Composition and I/O stay outside application services."""

from pathlib import Path


def register(parsers):
    from tram.metro_commands import register as register_metro

    register_metro(parsers)
    occupancy = parsers.add_parser(
        "export-occupancy",
        help="Export vehicle-time-weighted segment estimates as a prepared bundle",
    )
    occupancy.add_argument("directory", type=Path)
    occupancy.add_argument("--trip-id", action="append", required=True)
    occupancy.add_argument("--revision", required=True)
    occupancy.add_argument("--from", dest="start", required=True)
    occupancy.add_argument("--to", dest="end", required=True)
    occupancy.add_argument("--resolution", choices=["hour", "day", "month"], default="hour")
    occupancy.add_argument(
        "--metric", choices=["occupancy", "occupancy_ratio"], default="occupancy"
    )
    evaluate = parsers.add_parser(
        "evaluate", help="Backtest seasonal baseline without training; publish a report"
    )
    evaluate.add_argument("--dataset", required=True)
    evaluate.add_argument("--profile", required=True)
    evaluate.add_argument(
        "--origin",
        action="append",
        required=True,
        help="RFC3339 fold start; repeat in increasing order",
    )
    prepare = parsers.add_parser("prepare-csv", help="Convert aggregate CSV into a prepared bundle")
    prepare.add_argument("manifest", type=Path)
    prepare.add_argument("csv", type=Path)
    prepare.add_argument("directory", type=Path)
    context = parsers.add_parser(
        "context-refresh", help="Fetch weather/events and store an immutable snapshot"
    )
    context.add_argument("request", type=Path, help="RefreshContext JSON request")
    geo = parsers.add_parser("import-geo", help="Import a Moscow open-data GeoJSON point export")
    geo.add_argument("path", type=Path)
    geo.add_argument("--source-url", required=True)
    geo.add_argument("--category", required=True, choices=["metro", "hub", "poi"])
    geo.add_argument("--id-field", required=True)
    geo.add_argument("--name-field", required=True)
    replay = parsers.add_parser(
        "replay-trip", help="Replay an ordered event journal into an explicit trip ID"
    )
    replay.add_argument("plan", type=Path)
    replay.add_argument("events", type=Path)


def execute(args):
    if args.command in ("prepare-metro", "evaluate-metro"):
        from tram.metro_commands import execute as execute_metro

        return execute_metro(args)

    import json

    from tram.application.occupancy import OccupancyService
    from tram.application.service import ReadService
    from tram.composition import build_context
    from tram.infrastructure.contract import Contract, strict_json
    from tram.infrastructure.database import make_engine, session_factory
    from tram.infrastructure.geo_import import read_geojson
    from tram.infrastructure.repository import SqlRepository
    from tram.infrastructure.runtime import SignedCursor, SystemClock
    from tram.infrastructure.settings import Settings
    from tram.infrastructure.trips import SqlTripStore

    settings, clock = Settings(), SystemClock()
    contract = Contract(settings.openapi_path)
    if args.command == "prepare-csv":
        from tram.infrastructure.csv_import import prepare_csv

        count = prepare_csv(args.manifest, args.csv, args.directory, contract)
        print(f"Prepared {count} observations in {args.directory}; run publish for semantic checks")
        return 0
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        sessions = session_factory(engine)
        reads = ReadService(SqlRepository(sessions), clock, SignedCursor("unused-cli-cursor-" * 3))
        service = build_context(settings, sessions, clock, reads)
        if args.command == "export-occupancy":
            from tram.application.occupancy_export import export_occupancy

            service = OccupancyService(SqlTripStore(sessions), clock, reads)
            manifest, records = export_occupancy(
                service,
                reads,
                args.trip_id,
                args.revision,
                args.start,
                args.end,
                args.resolution,
                args.metric,
            )
            contract.validate("Capabilities", manifest["capabilities"])
            args.directory.mkdir(parents=True, exist_ok=False)
            with (args.directory / "observations.jsonl").open(
                "x", encoding="utf-8", newline="\n"
            ) as stream:
                for record in records:
                    contract.validate("ObservationPoint", record["point"])
                    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            (args.directory / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Exported estimates to {args.directory}; run publish after review")
            return 0
        if args.command == "evaluate":
            from tram_ml.baseline import SeasonalNaive
            from tram_ml.evaluation import score, temporal_folds

            from tram.application.evaluation import EvaluateBaseline
            from tram.infrastructure.evaluation import SqlEvaluationStore

            runner = EvaluateBaseline(
                reads.repository,
                SqlEvaluationStore(sessions, contract),
                reads,
                clock,
                SeasonalNaive(),
                temporal_folds,
                score,
            )
            report = runner.execute(args.dataset, args.profile, args.origin)
            print(
                json.dumps(
                    {
                        "id": report["summary"]["id"],
                        "status": report["summary"]["status"],
                        "scores": report["scores"],
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "context-refresh":
            command = strict_json(args.request.read_bytes())
            contract.validate("RefreshContext", command)
            result = service.refresh(command)
            print(
                json.dumps(
                    {
                        k: result[k]
                        for k in ("id", "provider", "status", "record_count", "warnings")
                    },
                    ensure_ascii=False,
                )
            )
            return int(result["status"] != "succeeded")
        if args.command == "import-geo":
            payload = read_geojson(
                args.path, args.source_url, args.category, args.id_field, args.name_field
            )
            result = service.capture("data.mos.ru", payload)
            print(f"Imported snapshot {result['id']}: {result['record_count']} objects")
            return 0
        if args.command == "replay-trip":
            plan = strict_json(args.plan.read_bytes())
            contract.validate("CreateOccupancyTrip", plan)
            service = OccupancyService(SqlTripStore(sessions), clock, reads)
            service.create(plan)
            with args.events.open(encoding="utf-8") as stream:
                for line in stream:
                    event = strict_json(line)
                    contract.validate("OccupancyEvent", event)
                    service.apply(plan["trip_id"], event)
            print(json.dumps(service.get(plan["trip_id"])["state"], ensure_ascii=False))
            return 0
    finally:
        engine.dispose()
