"""Prepare the metro research dataset without I/O, DB access or fitting."""

from collections import Counter, defaultdict
from dataclasses import asdict

from tram.domain.errors import DomainError
from tram.domain.metro import (
    MetroEntrance,
    MetroFlow,
    QuarterlyPoint,
    quarter_grid,
    series_identity,
)


def prepare_metro(entrances: tuple[MetroEntrance, ...], flows: tuple[MetroFlow, ...]):
    if not entrances or not flows:
        raise DomainError("Both source datasets must be nonempty")
    for source in (entrances, flows):
        if len({row.source_id for row in source}) != len(source):
            raise DomainError("Duplicate source global_id")
    keyed = {(row.station, row.line, row.quarter): row for row in flows}
    if len(keyed) != len(flows):
        raise DomainError("Duplicate station/line/quarter; no implicit aggregation is allowed")
    periods = defaultdict(set)
    geo = defaultdict(list)
    for row in flows:
        periods[row.station, row.line].add(row.quarter)
    for entrance in entrances:
        geo[entrance.station, entrance.line].append(entrance)
    start = min(row.quarter for row in flows)
    end = max(row.quarter for row in flows).shift(1)
    if len(periods) * (end.ordinal - start.ordinal) > 1_000_000:
        raise DomainError("Dense research grid would exceed one million rows")
    grid = quarter_grid(start, end)
    records, registry, issues = [], [], []
    for (station, line), present in sorted(periods.items()):
        identity = series_identity(station, line)
        matched = sorted(geo[station, line], key=lambda row: row.source_id)
        registry.append(
            {
                "series_id": identity,
                "station_name": station,
                "line_name": line,
                "identity_policy": "exact_source_labels_v1",
                "physical_station_id": None,
                "first_quarter": str(min(present)),
                "last_quarter": str(max(present)),
                "observed_quarters": len(present),
                "complete_source_span": len(present) == len(grid),
                "geo_match": "exact_labels" if matched else "unresolved",
                "entrance_ids": [row.source_id for row in matched],
            }
        )
        if not matched:
            issues.append(
                {
                    "kind": "unresolved_geo_match",
                    "series_id": identity,
                    "station_name": station,
                    "line_name": line,
                    "candidate_geo_lines": sorted(
                        {r.line for r in entrances if r.station == station}
                    ),
                    "resolution": "pending_evidence; candidates_are_not_accepted_matches",
                }
            )
        for quarter in grid:
            row = keyed.get((station, line, quarter))
            reason = (
                None
                if row
                else "missing_source_period"
                if min(present) < quarter < max(present)
                else "outside_source_span"
            )
            point = QuarterlyPoint(
                identity,
                quarter,
                row.incoming if row else None,
                row.outgoing if row else None,
                reason,
            )
            flags = [reason] if reason else []
            if row and row.incoming == row.outgoing == 0:
                flags.append("zero_flow_unverified")
            record = asdict(point) | {
                "quarter": str(quarter),
                "source_record_id": row.source_id if row else None,
                "value_kind": "observed" if row else "missing",
                "quality_flags": flags,
            }
            records.append(record)
            for flag in flags:
                issues.append({"kind": flag, "series_id": identity, "quarter": str(quarter)})
    features = []
    for row in sorted(entrances, key=lambda row: row.source_id):
        features.append(
            {
                "type": "Feature",
                "id": str(row.source_id),
                "geometry": {"type": "Point", "coordinates": [row.longitude, row.latitude]},
                "properties": {
                    "global_id": row.source_id,
                    "Name": row.name,
                    "NameOfStation": row.station,
                    "Line": row.line,
                    "ObjectStatus": row.status,
                    "OnTerritoryOfMoscow": row.in_moscow,
                    "label_pair_id": series_identity(row.station, row.line),
                },
            }
        )
    coincident = defaultdict(list)
    for row in entrances:
        coincident[row.longitude, row.latitude].append(row.source_id)
    return {
        "entrances.geojson": {"type": "FeatureCollection", "features": features},
        "series.json": registry,
        "quarters.jsonl": records,
        "quality.json": {
            "flow_rows": len(flows),
            "entrance_rows": len(entrances),
            "series_count": len(registry),
            "quarter_start": str(start),
            "quarter_end_exclusive": str(end),
            "quarter_count": len(grid),
            "dense_rows": len(records),
            "complete_series_count": sum(row["complete_source_span"] for row in registry),
            "issue_counts": dict(sorted(Counter(row["kind"] for row in issues).items())),
            "issues": issues,
            "entrance_status_counts": dict(
                sorted(Counter(row.status for row in entrances).items())
            ),
            "outside_moscow_entrances": sum(not row.in_moscow for row in entrances),
            "coincident_coordinates": [
                {"coordinates": list(coords), "entrance_ids": sorted(ids)}
                for coords, ids in sorted(coincident.items())
                if len(ids) > 1
            ],
            "policy": {
                "zeros": "preserve_observed_value_and_flag; reason_unknown",
                "missing_periods": "insert_nulls_and_reason; no_imputation",
                "unmatched_stations": "preserve_series; no_fuzzy_join",
                "geo": "current_snapshot; not_a_historical_feature",
                "renames": "require_an_explicit_reviewed_crosswalk; not_inferred",
                "closed_entrances": "preserve_source_status; no_implicit_filter",
            },
        },
    }
