"""Composition root for offline metro preparation and seasonal evaluation."""

import json
from datetime import UTC, datetime
from pathlib import Path


def register(parsers):
    prepare = parsers.add_parser(
        "prepare-metro", help="Prepare official 624/62743 JSON snapshots; no DB or training"
    )
    prepare.add_argument("geo", type=Path)
    prepare.add_argument("flow", type=Path)
    prepare.add_argument("directory", type=Path)
    prepare.add_argument("--revision", required=True)
    evaluate = parsers.add_parser(
        "evaluate-metro", help="Split and evaluate a quarterly retrospective baseline; no training"
    )
    evaluate.add_argument("prepared", type=Path)
    evaluate.add_argument("directory", type=Path)
    evaluate.add_argument("--revision", required=True)
    evaluate.add_argument("--train-start", required=True, help="YYYY-Qn, inclusive")
    evaluate.add_argument("--validation-start", required=True, help="YYYY-Qn, inclusive")
    evaluate.add_argument("--test-start", required=True, help="YYYY-Qn, inclusive")
    evaluate.add_argument("--test-end", required=True, help="YYYY-Qn, exclusive")
    evaluate.add_argument("--metric", choices=["incoming", "outgoing"], default="incoming")


def execute(args):
    from tram.infrastructure.metro_files import (
        read_entrances,
        read_flows,
        read_prepared,
        write_bundle,
    )

    metadata = {
        "revision": args.revision,
        "created_at": datetime.now(UTC).isoformat(),
        "training_performed": False,
        "mode": "retrospective_snapshot",
        "limitations": [
            "This is a metro experiment, not observed tram occupancy",
            "Current releases may revise old quarters; historical publication times are unverified",
            "Geo data is a current snapshot and is not used as a historical baseline feature",
            "Exact label-pair IDs do not resolve physical station identity or historical renames",
        ],
    }
    if args.command == "prepare-metro":
        from tram.application.metro import prepare_metro

        entrances, geo_source = read_entrances(args.geo)
        flows, flow_source = read_flows(args.flow)
        documents = prepare_metro(entrances, flows)
        metadata |= {"kind": "metro_research_bundle_v1", "sources": [geo_source, flow_source]}
        write_bundle(args.directory, documents, metadata)
        counts = documents["quality.json"]["issue_counts"]
        print(
            json.dumps(
                {"directory": str(args.directory), "mode": metadata["mode"], "issues": counts},
                ensure_ascii=False,
            )
        )
        return 0
    from tram_ml.quarterly import evaluate_quarterly

    from tram.domain.metro import Quarter, QuarterSplit

    manifest, points, digest = read_prepared(args.prepared)
    split = QuarterSplit(
        *(
            Quarter.parse(value)
            for value in (args.train_start, args.validation_start, args.test_start, args.test_end)
        )
    )
    documents = evaluate_quarterly(points, split, args.metric)
    metadata |= {
        "kind": "metro_quarterly_evaluation_v1",
        "dataset_revision": manifest["revision"],
        "dataset_manifest_sha256": digest,
        "method": "metro_quarterly_seasonal_naive_v1",
        "metric": args.metric,
        "sources": manifest["sources"],
        "historical_availability_verified": False,
    }
    write_bundle(args.directory, documents, metadata)
    totals = [r for r in documents["scores.json"] if r["series_id"] is None]
    print(
        json.dumps(
            {"directory": str(args.directory), "mode": metadata["mode"], "scores": totals},
            ensure_ascii=False,
        )
    )
    return 0
