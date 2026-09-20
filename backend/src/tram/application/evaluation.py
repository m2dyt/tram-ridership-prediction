"""Orchestrate temporal baseline evaluation through injected data and ML ports."""

from dataclasses import asdict
from uuid import uuid4

from tram.application.errors import ApplicationError
from tram.application.mapping import spatial_document, spatial_from_document
from tram.application.service import required
from tram.domain.time import MOSCOW, Horizon, Interval, Resolution, parse_time


class EvaluateBaseline:
    def __init__(self, repository, store, reads, clock, predictor, folds, score):
        self.repository, self.store, self.reads, self.clock = repository, store, reads, clock
        self.predictor, self.make_folds, self.score = predictor, folds, score

    def execute(self, dataset_id, profile_id, origins):
        dataset = self.reads.dataset(dataset_id)
        caps = dataset["capabilities"]
        profile = required(
            next((p for p in caps["forecast_profiles"] if p["id"] == profile_id), None), "Profile"
        )
        observed = next(
            p for p in caps["observation_profiles"] if p["id"] == profile["observation_profile_id"]
        )
        if not origins or len(origins) > 100:
            raise ApplicationError("VALIDATION_ERROR", "Provide 1 to 100 increasing origins")
        folds = self.make_folds(
            Interval(parse_time(observed["history_start"]), parse_time(observed["history_end"])),
            [parse_time(o) for o in origins],
            Horizon(profile["horizon"]),
            Resolution(profile["resolution"]),
        )
        if any(f.test.end > self.clock.now() for f in folds):
            raise ApplicationError(
                "VALIDATION_ERROR", "Evaluation test horizons must be entirely in the past"
            )
        entries, fold_documents = [], []
        for index, fold in enumerate(folds, 1):
            fold_id = f"fold-{index}"
            model = {
                "id": "seasonal-naive",
                "version": "1",
                "method": "seasonal_naive_v1",
                "training_history_end": fold.as_of.isoformat(),
                "feature_set_version": "calendar-reference-v1",
                "is_baseline": True,
            }
            count = 0
            for series in self.repository.series(dataset_id, observed["id"], profile["route_ids"]):
                spatial = spatial_from_document(series["spatial"])
                history = self.repository.history(dataset_id, observed["id"], spatial, fold.as_of)
                actuals = self.store.actuals(
                    dataset_id, observed["id"], spatial, fold.test, self.clock.now()
                )
                predictions = self.predictor.predict(
                    history,
                    (spatial,),
                    fold.test,
                    Horizon(profile["horizon"]),
                    Resolution(profile["resolution"]),
                    fold.as_of,
                )
                for prediction in predictions:
                    actual = actuals.get(prediction.interval.start)
                    value = actual["value"] if actual else None
                    scored = value is not None and prediction.value is not None
                    entries.append(
                        {
                            "fold_id": fold_id,
                            "spatial": spatial_document(spatial),
                            "interval_start": prediction.interval.start.isoformat(),
                            "interval_end": prediction.interval.end.isoformat(),
                            "actual": value,
                            "actual_kind": actual["value_kind"] if actual else "observed",
                            "model": prediction.value,
                            "seasonal_naive": prediction.value,
                            "regression": None,
                            "prediction_interval": None,
                            "is_peak": profile["resolution"] == "hour"
                            and prediction.interval.start.astimezone(MOSCOW).hour
                            in (7, 8, 9, 17, 18, 19),
                            "scored": scored,
                            "exclusion_reason": None
                            if scored
                            else "actual_or_reference_unavailable",
                            "quality": {
                                "status": "ok" if scored else "missing",
                                "coverage_ratio": 1 if scored else 0,
                                "flags": [],
                            },
                        }
                    )
                    count += 1
                    if len(entries) > 1_000_000:
                        raise ApplicationError(
                            "VALIDATION_ERROR",
                            "Evaluation exceeds one million points; split routes/folds",
                        )
            fold_documents.append(
                {
                    "id": fold_id,
                    "as_of": fold.as_of.isoformat(),
                    "training_start": fold.training.start.isoformat(),
                    "training_end": fold.training.end.isoformat(),
                    "test_start": fold.test.start.isoformat(),
                    "test_end": fold.test.end.isoformat(),
                    "point_count": count,
                    "model": model,
                }
            )
        scores = []
        for route in [None, *profile["route_ids"]]:
            for demand_slice in ("all", "peak"):
                rows = [
                    p
                    for p in entries
                    if (route is None or p["spatial"]["route_id"] == route)
                    and (demand_slice == "all" or p["is_peak"])
                ]
                for method in ("model", "seasonal_naive"):
                    scores.append(
                        {
                            "method": method,
                            "route_id": route,
                            "demand_slice": demand_slice,
                            **asdict(
                                self.score([p["actual"] for p in rows], [p[method] for p in rows])
                            ),
                            "interval_coverage": None,
                            "mean_interval_width": None,
                        }
                    )
        summary = {
            "id": str(uuid4()),
            "dataset_revision_id": dataset_id,
            "network_revision_id": caps["network_revision_id"],
            "source_mode": caps["source_mode"],
            "profile": profile,
            "model": model,
            "status": "complete",
            "created_at": self.clock.now().isoformat(),
            "limitations": [
                "Baseline only; no trained model or regression",
                *profile.get("limitations", []),
            ],
        }
        report = {
            "summary": summary,
            "folds": fold_documents,
            "scores": scores,
            "peak_rule": "Hourly Moscow intervals starting at 07–09 or 17–19; daily/monthly peak slice is empty",
            "baseline_definitions": {
                "seasonal_naive": "Prior available week for day/month, prior year for year",
                "regression": None,
            },
            "feature_availability_policy": "History interval_end and available_at <= fold as_of; actuals available at report creation",
            "warnings": [
                "model equals seasonal_naive; no training was performed",
                "Overlapping folds count their forecasts separately",
                "External context is not used by seasonal baseline",
            ],
        }
        self.store.save(report, entries)
        return report
