"""Rolling one-quarter metro baseline on a retrospective snapshot; no fitting."""

from collections import defaultdict
from dataclasses import asdict

from tram.domain.errors import DomainError
from tram.domain.metro import QuarterlyPoint, QuarterSplit, quarter_grid

from tram_ml.evaluation import score


def evaluate_quarterly(points: tuple[QuarterlyPoint, ...], split: QuarterSplit, metric: str):
    if metric not in ("incoming", "outgoing") or not points:
        raise DomainError("Choose incoming or outgoing on a nonempty dataset")
    lookup = {(p.series_id, p.quarter): p for p in points}
    if len(lookup) != len(points):
        raise DomainError("Duplicate quarterly point")
    start, end = min(p.quarter for p in points), max(p.quarter for p in points).shift(1)
    if split.train_start < start or split.test_end > end:
        raise DomainError("The full split must be inside the prepared history")
    ids = sorted({p.series_id for p in points})
    grid = quarter_grid(start, end)
    if len(lookup) != len(ids) * len(grid):
        raise DomainError("Expected a dense grid with explicit null records")
    membership = []
    for p in sorted(points, key=lambda p: (p.quarter, p.series_id)):
        partition = split.partition(p.quarter)
        if partition:
            membership.append(
                {
                    "series_id": p.series_id,
                    "quarter": str(p.quarter),
                    "partition": partition,
                    "target_present": getattr(p, metric) is not None,
                }
            )
    predictions = []
    for quarter in quarter_grid(split.validation_start, split.test_end):
        reference = quarter.shift(-4)
        for identity in ids:
            target = lookup[identity, quarter]
            historical = (
                lookup.get((identity, reference)) if reference >= split.train_start else None
            )
            prediction = getattr(historical, metric) if historical else None
            predictions.append(
                {
                    "series_id": identity,
                    "quarter": str(quarter),
                    "partition": split.partition(quarter),
                    "actual": getattr(target, metric),
                    "prediction": prediction,
                    "target_missing_reason": target.missing_reason,
                    "prediction_missing_reason": "seasonal_reference_missing"
                    if prediction is None
                    else None,
                    "reference_quarter": str(reference),
                    "forecast_origin": quarter.start.isoformat(),
                }
            )
    groups = defaultdict(list)
    for row in predictions:
        groups[row["partition"], None].append(row)
        groups[row["partition"], row["series_id"]].append(row)
    scores = []
    for (partition, identity), rows in sorted(
        groups.items(), key=lambda item: (item[0][0], item[0][1] or "")
    ):
        observed = sum(r["actual"] is not None for r in rows)
        result = score([r["actual"] for r in rows], [r["prediction"] for r in rows])
        scores.append(
            {
                "partition": partition,
                "series_id": identity,
                **asdict(result),
                "total_points": len(rows),
                "observed_points": observed,
                "prediction_points": sum(r["prediction"] is not None for r in rows),
                "coverage_on_observed": result.sample_count / observed if observed else None,
            }
        )
    boundaries = {k: str(v) for k, v in vars(split).items()}
    return {
        "splits.json": {
            "boundaries": boundaries,
            "interval_convention": "start_inclusive_end_exclusive",
            "horizon": "one_quarter",
            "evaluation_protocol": "rolling_origin; previous observed quarters may become references",
            "metric": metric,
            "fit_executed": False,
        },
        "membership.jsonl": membership,
        "predictions.jsonl": predictions,
        "scores.json": scores,
    }
