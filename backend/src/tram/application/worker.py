import logging
from collections.abc import Mapping

from tram.application.errors import ApplicationError
from tram.application.mapping import spatial_document, spatial_from_document
from tram.application.models import BUNDLE_METHOD, SEASONAL_METHOD
from tram.application.ports import Clock, Predictor, Repository
from tram.domain.time import Horizon, Interval, Resolution, parse_time

LOGGER = logging.getLogger(__name__)


class RunWorker:
    """Execute queued runs with exactly the model pinned in each run.

    ``predictors`` maps a ModelReference.method to the predictor that
    implements it. A single predictor is accepted for backwards compatibility
    and registered under its own ``method`` attribute. A run whose method has
    no predictor here, or whose bundle version differs from the loaded one,
    fails with MODEL_UNAVAILABLE instead of being computed by another model.
    """

    def __init__(
        self,
        repository: Repository,
        clock: Clock,
        predictors: Predictor | Mapping[str, Predictor],
        lease_seconds=120,
        max_attempts=3,
    ):
        self.repository, self.clock = repository, clock
        if isinstance(predictors, Mapping):
            self.predictors = dict(predictors)
        else:
            self.predictors = {getattr(predictors, "method", SEASONAL_METHOD): predictors}
        self.lease_seconds, self.max_attempts = lease_seconds, max_attempts

    def _predictor_for(self, model):
        method = model["method"]
        predictor = self.predictors.get(method)
        if predictor is None:
            if method == BUNDLE_METHOD:
                raise ApplicationError(
                    "MODEL_UNAVAILABLE",
                    f"Model bundle {model['version']} is not loaded by this worker; see the "
                    "worker log for why it was rejected at startup, fix it and restart the worker",
                )
            raise ApplicationError(
                "MODEL_UNAVAILABLE", f"Worker has no predictor for model method {method}"
            )
        if method == BUNDLE_METHOD and getattr(predictor, "version", None) != model["version"]:
            raise ApplicationError(
                "MODEL_UNAVAILABLE",
                f"Run requires model bundle {model['version']}, the worker serves "
                f"{getattr(predictor, 'version', None)}; restart the worker after "
                "switching the active version",
            )
        return predictor

    def execute_one(self) -> bool:
        claim = self.repository.claim(self.clock.now(), self.lease_seconds, self.max_attempts)
        if not claim:
            return False
        run, token = claim["run"], claim["lease_token"]
        try:
            predictor = self._predictor_for(run["model"])
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
                try:
                    predictions = predictor.predict(
                        history,
                        (spatial,),
                        Interval(
                            parse_time(run["forecast_start"]), parse_time(run["forecast_end"])
                        ),
                        Horizon(profile["horizon"]),
                        Resolution(profile["resolution"]),
                        as_of,
                    )
                except Exception as exc:
                    if run["model"]["method"] != BUNDLE_METHOD:
                        raise
                    # A bundle failure must not become a seasonal forecast labelled as
                    # the bundle; fail the run explicitly and keep details in the log.
                    LOGGER.error(
                        "run_id=%s bundle=%s prediction failed: %s",
                        run["id"],
                        run["model"]["version"],
                        type(exc).__name__,
                    )
                    raise ApplicationError(
                        "MODEL_UNAVAILABLE",
                        f"Model bundle {run['model']['version']} failed to produce a forecast",
                    ) from exc
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
