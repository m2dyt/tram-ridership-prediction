from tram.application.errors import ApplicationError
from tram.application.mapping import spatial_document, spatial_from_document
from tram.application.ports import Clock, Predictor, Repository
from tram.domain.time import Horizon, Interval, Resolution, parse_time


class RunWorker:
    def __init__(
        self,
        repository: Repository,
        clock: Clock,
        predictor: Predictor,
        lease_seconds=120,
        max_attempts=3,
    ):
        self.repository, self.clock, self.predictor = repository, clock, predictor
        self.lease_seconds, self.max_attempts = lease_seconds, max_attempts

    def execute_one(self) -> bool:
        claim = self.repository.claim(self.clock.now(), self.lease_seconds, self.max_attempts)
        if not claim:
            return False
        run, token = claim["run"], claim["lease_token"]
        try:
            if run["model"]["method"] != "seasonal_naive_v1":
                raise ApplicationError("MODEL_UNAVAILABLE", "Worker does not support this model")
            profile = run["profile"]
            series = self.repository.series(
                run["dataset_revision_id"], profile["observation_profile_id"], run["route_ids"]
            )
            if not series:
                raise ApplicationError("INSUFFICIENT_HISTORY", "No series available")
            points = []
            for item in series:
                if not self.repository.heartbeat(
                    run["id"], token, self.clock.now(), self.lease_seconds
                ):
                    return True  # Lease lost: a different worker owns this run.
                spatial = spatial_from_document(item["spatial"])
                as_of = parse_time(run["as_of"])
                history = self.repository.history(
                    run["dataset_revision_id"], profile["observation_profile_id"], spatial, as_of
                )
                predictions = self.predictor.predict(
                    history,
                    (spatial,),
                    Interval(parse_time(run["forecast_start"]), parse_time(run["forecast_end"])),
                    Horizon(profile["horizon"]),
                    Resolution(profile["resolution"]),
                    as_of,
                )
                for prediction in predictions:
                    points.append(
                        {
                            "spatial": spatial_document(prediction.spatial),
                            "interval_start": prediction.interval.start.isoformat(),
                            "interval_end": prediction.interval.end.isoformat(),
                            "value": prediction.value,
                            "missing_reason": prediction.missing_reason,
                            "value_kind": "forecast",
                            "prediction_interval": None,
                            "quality": {
                                "status": "missing" if prediction.value is None else "ok",
                                "coverage_ratio": 0 if prediction.value is None else 1,
                                "flags": ["reference_observation_unavailable"]
                                if prediction.value is None
                                else [],
                            },
                        }
                    )
            self.repository.complete(run["id"], token, points, self.clock.now())
        except ApplicationError as error:
            self.repository.fail(run["id"], token, self.clock.now(), error.code, error.message)
        return True
