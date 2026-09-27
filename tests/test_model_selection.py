"""The model is pinned when a run is created and executed as-is by the worker.

Covers the bundle catalog (metadata only), model selection rules, worker
provenance (no silent substitution), the worker startup policy for an
unusable bundle, /health readiness, and one real exported baseline bundle.
"""

import copy
import logging

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from tram.api.app import create_http_app
from tram.api.extensions import auth_bindings, context_bindings, occupancy_bindings
from tram.application.auth import AuthService
from tram.application.context import ContextService
from tram.application.errors import ApplicationError
from tram.application.models import (
    BUNDLE_METHOD,
    SEASONAL_METHOD,
    SEASONAL_WARNING,
    model_readiness,
    select_model,
)
from tram.application.occupancy import OccupancyService
from tram.application.service import ForecastService, ReadService
from tram.application.worker import RunWorker
from tram.composition import ModelBundleUnavailable, worker_predictors
from tram.domain.series import Prediction, SpatialKey, SpatialLevel
from tram.domain.time import MOSCOW, Horizon, Resolution, forecast_window, intervals, parse_time
from tram.infrastructure.auth import (
    Argon2PasswordHasher,
    JwtTokenIssuer,
    SqlSessionStore,
    SqlUserRepository,
)
from tram.infrastructure.context_store import SqlSnapshotStore
from tram.infrastructure.contract import Contract
from tram.infrastructure.database import Base, make_engine, session_factory
from tram.infrastructure.login_attempts import SqlLoginAttemptStore
from tram.infrastructure.ml import model_catalog
from tram.infrastructure.ml.artifact_predictor import ArtifactPredictor
from tram.infrastructure.ml.model_catalog import DEFAULT_BUNDLE_ROUTES, FileModelCatalog
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SignedCursor
from tram.infrastructure.settings import Settings
from tram.infrastructure.sources import ExternalSources
from tram.infrastructure.trips import SqlTripStore
from tram_ml.baseline import SeasonalNaive

from ml.training.tram.baseline import calculate_historical_profiles
from ml.training.tram.bundle import export_model_bundle, set_active_version
from ml.training.tram.features import ALL_ROUTES, add_calendar_features, generate_full_grid
from tests.support import ROOT, FrozenClock, seed_trusted_fixture

HISTORY_END = "2025-09-01T00:00:00+03:00"
AS_OF = "2026-09-20T18:00:00+03:00"
MARKER = 987654.0


def export(models_root, version="bundle_v1", profiles=None, **config):
    return export_model_bundle(
        version,
        models=None,
        profiles=profiles or {},
        metrics={"overall": {}},
        config={"model_type": "baseline", **config},
        models_root=models_root,
    )


def ok_bundle(routes=("17",), history_end=HISTORY_END, is_baseline=False, version="bundle_v1"):
    return {
        "status": "ok",
        "version": version,
        "reason": None,
        "routes": list(routes),
        "model_type": "baseline" if is_baseline else "catboost",
        "model": {
            "id": version,
            "version": version,
            "method": BUNDLE_METHOD,
            "training_history_end": history_end,
            "feature_set_version": "features-test",
            "is_baseline": is_baseline,
        },
    }


INVALID = {"status": "invalid", "version": "bundle_v1", "reason": "checksum mismatch: x"}
NOT_CONFIGURED = {"status": "not_configured", "version": None, "reason": None}


# --- catalog -------------------------------------------------------------------------


def test_default_bundle_routes_match_training_routes():
    assert list(DEFAULT_BUNDLE_ROUTES) == ALL_ROUTES


def test_catalog_without_bundle_is_not_configured(tmp_path):
    assert FileModelCatalog(tmp_path / "models").active_bundle()["status"] == "not_configured"


def test_catalog_describes_valid_bundle(tmp_path):
    root = tmp_path / "models"
    export(root, training_history_end=HISTORY_END)
    set_active_version("bundle_v1", models_root=root)
    bundle = FileModelCatalog(root).active_bundle()
    assert bundle["status"] == "ok"
    assert bundle["model"]["method"] == BUNDLE_METHOD
    assert bundle["model"]["version"] == "bundle_v1"
    assert parse_time(bundle["model"]["training_history_end"]) == parse_time(HISTORY_END)
    assert bundle["model"]["is_baseline"] is True
    assert bundle["model"]["feature_set_version"].startswith("features-")
    assert "17" in bundle["routes"] and "5" in bundle["routes"]


def test_catalog_requires_training_history_end(tmp_path):
    root = tmp_path / "models"
    export(root)
    set_active_version("bundle_v1", models_root=root)
    bundle = FileModelCatalog(root).active_bundle()
    assert bundle["status"] == "invalid"
    assert "training_history_end" in bundle["reason"]


def test_catalog_detects_tampering_after_caching(tmp_path):
    root = tmp_path / "models"
    bundle_dir = export(root, training_history_end=HISTORY_END)
    set_active_version("bundle_v1", models_root=root)
    catalog = FileModelCatalog(root)
    assert catalog.active_bundle()["status"] == "ok"
    with (bundle_dir / "estimator.joblib").open("ab") as stream:
        stream.write(b"tampered")
    bundle = catalog.active_bundle()
    assert bundle["status"] == "invalid"
    assert "estimator" in bundle["reason"]


def test_configured_version_overrides_active_pointer(tmp_path):
    root = tmp_path / "models"
    export(root, "bundle_v1", training_history_end=HISTORY_END)
    export(root, "bundle_v2", training_history_end=HISTORY_END)
    set_active_version("bundle_v1", models_root=root)
    assert FileModelCatalog(root, "bundle_v2").active_bundle()["version"] == "bundle_v2"


def test_pointer_to_missing_bundle_is_invalid(tmp_path):
    root = tmp_path / "models"
    set_active_version("missing_v1", models_root=root)
    bundle = FileModelCatalog(root).active_bundle()
    assert bundle["status"] == "invalid" and bundle["version"] == "missing_v1"


def test_bundle_needing_an_absent_library_is_invalid(tmp_path, monkeypatch):
    root = tmp_path / "models"
    export(root, model_type="catboost", training_history_end=HISTORY_END)
    set_active_version("bundle_v1", models_root=root)
    monkeypatch.setattr(model_catalog.importlib.util, "find_spec", lambda name: None)
    bundle = FileModelCatalog(root).active_bundle()
    assert bundle["status"] == "invalid"
    assert "catboost" in bundle["reason"]


# --- selection -----------------------------------------------------------------------

PROFILE = {"id": "p-day", "resolution": "hour"}
SEASONAL = {
    "profile_ids": ["p-day"],
    "model": {
        "id": "baseline-day",
        "version": "1",
        "method": SEASONAL_METHOD,
        "training_history_end": "2026-09-01T00:00:00+03:00",
        "feature_set_version": "calendar",
        "is_baseline": True,
    },
}


def choose(bundle, profile=PROFILE, route_ids=("17",), fallback=True):
    return select_model(
        profile=profile,
        route_ids=list(route_ids),
        as_of=parse_time(AS_OF),
        dataset_models=[SEASONAL],
        bundle=bundle,
        fallback_to_seasonal_naive=fallback,
    )


def test_eligible_bundle_is_pinned():
    model, warnings = choose(ok_bundle())
    assert model["method"] == BUNDLE_METHOD and model["version"] == "bundle_v1"
    assert SEASONAL_WARNING not in warnings


def test_baseline_bundle_is_labelled_as_unfitted():
    _, warnings = choose(ok_bundle(is_baseline=True))
    assert any("no model was fitted" in w for w in warnings)


@pytest.mark.parametrize(
    "bundle,profile,route_ids,expected",
    [
        (ok_bundle(), {"id": "p-day", "resolution": "day"}, ("17",), "resolution is day"),
        (ok_bundle(), PROFILE, ("demo-route-01",), "route demo-route-01"),
        (ok_bundle(history_end="2026-09-21T00:00:00+03:00"), PROFILE, ("17",), "after as_of"),
        (INVALID, PROFILE, ("17",), "invalid and was not used"),
    ],
)
def test_seasonal_baseline_is_chosen_with_an_explicit_reason(bundle, profile, route_ids, expected):
    model, warnings = choose(bundle, profile=profile, route_ids=route_ids)
    assert model["method"] == SEASONAL_METHOD
    assert warnings[0] == SEASONAL_WARNING
    assert expected in warnings[1]


def test_no_configured_bundle_keeps_the_seasonal_warning_only():
    model, warnings = choose(NOT_CONFIGURED)
    assert model["method"] == SEASONAL_METHOD and warnings == [SEASONAL_WARNING]


def test_invalid_bundle_without_fallback_rejects_hourly_runs():
    with pytest.raises(ApplicationError) as error:
        choose(INVALID, fallback=False)
    assert error.value.code == "MODEL_UNAVAILABLE"


def test_invalid_bundle_without_fallback_keeps_profiles_it_never_serves():
    model, _ = choose(INVALID, profile={"id": "p-day", "resolution": "day"}, fallback=False)
    assert model["method"] == SEASONAL_METHOD


@pytest.mark.parametrize(
    "bundle,fallback,state,ready",
    [
        (NOT_CONFIGURED, True, "not_configured", True),
        (ok_bundle(), False, "ok", True),
        (INVALID, True, "fallback", True),
        (INVALID, False, "invalid", False),
    ],
)
def test_model_readiness(bundle, fallback, state, ready):
    assert model_readiness(bundle, fallback) == {
        "model": state,
        "model_version": bundle["version"],
        "ready": ready,
    }


# --- worker provenance ---------------------------------------------------------------


class FakeCatalog:
    def __init__(self, bundle):
        self.bundle = bundle

    def active_bundle(self):
        return copy.deepcopy(self.bundle)


class MarkerBundlePredictor:
    """Stands in for ArtifactPredictor: every value is MARKER, so its use is visible."""

    method = BUNDLE_METHOD

    def __init__(self, version="bundle_v1", error=None):
        self.version, self.error = version, error

    def predict(self, history, series, window, horizon, resolution, as_of):
        if self.error:
            raise self.error
        return tuple(
            Prediction(spatial, interval, MARKER, None, as_of)
            for interval in intervals(window, resolution)
            for spatial in series
        )


@pytest.fixture
def pipeline():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    seed_trusted_fixture(sessions)
    repo, clock = SqlRepository(sessions), FrozenClock()
    reads = ReadService(repo, clock, SignedCursor("c" * 32))
    yield repo, clock, reads, sessions
    engine.dispose()


def create_day_run(pipeline, bundle, key="model-selection-01", fallback=True):
    repo, clock, reads, _ = pipeline
    caps = reads.capabilities({})
    profile = next(p for p in caps["forecast_profiles"] if p["horizon"] == "day")
    service = ForecastService(
        repo, clock, reads, models=FakeCatalog(bundle), fallback_to_seasonal_naive=fallback
    )
    run, created = service.create(
        {
            "dataset_revision_id": caps["dataset_revision_id"],
            "profile_id": profile["id"],
            "route_ids": profile["route_ids"],
            "as_of": AS_OF,
            "forecast_start": "2026-09-21T00:00:00+03:00",
        },
        "operator",
        key,
    )
    assert created
    return run


def fixture_bundle(pipeline, **kwargs):
    _, _, reads, _ = pipeline
    caps = reads.capabilities({})
    profile = next(p for p in caps["forecast_profiles"] if p["horizon"] == "day")
    return ok_bundle(routes=profile["route_ids"], **kwargs)


def execute(pipeline, predictors, run):
    repo, clock, _, _ = pipeline
    assert RunWorker(repo, clock, predictors).execute_one()
    stored = repo.run(run["id"])
    points = repo.forecast_points(run["id"], {}, 0, 1000) if stored["status"] == "succeeded" else []
    return stored, points


BOTH = {SEASONAL_METHOD: SeasonalNaive(), BUNDLE_METHOD: MarkerBundlePredictor()}


def test_seasonal_run_is_not_computed_by_a_loaded_bundle(pipeline):
    run = create_day_run(pipeline, NOT_CONFIGURED)
    assert run["model"]["method"] == SEASONAL_METHOD
    stored, points = execute(pipeline, BOTH, run)
    assert stored["status"] == "succeeded"
    assert points and all(p["value"] != MARKER for p in points)


def test_bundle_run_is_computed_by_the_pinned_bundle(pipeline):
    run = create_day_run(pipeline, fixture_bundle(pipeline))
    assert run["model"]["method"] == BUNDLE_METHOD
    assert run["model"]["version"] == "bundle_v1"
    assert SEASONAL_WARNING not in run["warnings"]
    stored, points = execute(pipeline, BOTH, run)
    assert stored["status"] == "succeeded"
    assert stored["model"]["version"] == "bundle_v1"
    assert points and all(p["value"] == MARKER for p in points)


@pytest.mark.parametrize(
    "predictors,message",
    [
        (
            {SEASONAL_METHOD: SeasonalNaive(), BUNDLE_METHOD: MarkerBundlePredictor("bundle_v2")},
            "restart the worker",
        ),
        ({SEASONAL_METHOD: SeasonalNaive()}, "is not loaded by this worker"),
        (
            {
                SEASONAL_METHOD: SeasonalNaive(),
                BUNDLE_METHOD: MarkerBundlePredictor(error=RuntimeError("internal detail")),
            },
            "failed to produce a forecast",
        ),
    ],
)
def test_unavailable_bundle_fails_the_run_instead_of_substituting(pipeline, predictors, message):
    run = create_day_run(pipeline, fixture_bundle(pipeline))
    stored, _ = execute(pipeline, predictors, run)
    assert stored["status"] == "failed"
    assert stored["failure"]["code"] == "MODEL_UNAVAILABLE"
    assert message in stored["failure"]["message"]
    assert "internal detail" not in stored["failure"]["message"]


def test_legacy_single_predictor_worker_still_serves_seasonal_runs(pipeline):
    run = create_day_run(pipeline, NOT_CONFIGURED)
    stored, _ = execute(pipeline, SeasonalNaive(), run)
    assert stored["status"] == "succeeded"


def test_strict_policy_rejects_hourly_runs_when_the_bundle_is_invalid(pipeline):
    with pytest.raises(ApplicationError) as error:
        create_day_run(pipeline, INVALID, fallback=False)
    assert error.value.code == "MODEL_UNAVAILABLE"


# --- worker startup policy -----------------------------------------------------------


def settings(tmp_path, fallback=True, version=None):
    return Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        models_root=tmp_path / "models",
        fallback_to_seasonal_naive=fallback,
        model_version=version,
    )


def test_worker_without_bundle_serves_the_seasonal_baseline(tmp_path):
    predictors, bundle = worker_predictors(settings(tmp_path))
    assert set(predictors) == {SEASONAL_METHOD} and bundle["status"] == "not_configured"


def test_worker_loads_a_valid_bundle(tmp_path):
    export(tmp_path / "models", training_history_end=HISTORY_END)
    predictors, bundle = worker_predictors(settings(tmp_path, version="bundle_v1"))
    assert bundle["status"] == "ok"
    assert predictors[BUNDLE_METHOD].version == "bundle_v1"
    assert predictors[BUNDLE_METHOD].fallback is None


def test_worker_with_invalid_bundle_and_fallback_logs_and_serves_seasonal(tmp_path, caplog):
    set_active_version("missing_v1", models_root=tmp_path / "models")
    with caplog.at_level(logging.ERROR):
        predictors, bundle = worker_predictors(settings(tmp_path))
    assert set(predictors) == {SEASONAL_METHOD} and bundle["status"] == "invalid"
    assert "missing_v1" in caplog.text


def test_worker_with_invalid_bundle_and_no_fallback_refuses_to_start(tmp_path):
    set_active_version("missing_v1", models_root=tmp_path / "models")
    with pytest.raises(
        ModelBundleUnavailable, match="fallback to the seasonal baseline is disabled"
    ):
        worker_predictors(settings(tmp_path, fallback=False))


def test_worker_treats_an_unloadable_estimator_as_invalid(tmp_path, monkeypatch):
    export(tmp_path / "models", training_history_end=HISTORY_END)

    def broken(models_root, version):
        raise ModuleNotFoundError("catboost")

    monkeypatch.setattr(ArtifactPredictor, "from_version", broken)
    predictors, bundle = worker_predictors(settings(tmp_path, version="bundle_v1"))
    assert set(predictors) == {SEASONAL_METHOD}
    assert "ModuleNotFoundError" in bundle["reason"]
    with pytest.raises(ModelBundleUnavailable):
        worker_predictors(settings(tmp_path, fallback=False, version="bundle_v1"))


# --- /health readiness ---------------------------------------------------------------


def health_client(pipeline, status):
    repo, clock, reads, sessions = pipeline
    contract = Contract(ROOT / "openapi.yaml")
    extra_reads, extra_commands = occupancy_bindings(
        OccupancyService(SqlTripStore(sessions), clock, reads)
    )
    context_reads, context_commands = context_bindings(
        ContextService(SqlSnapshotStore(sessions), ExternalSources(), clock, reads)
    )
    auth_service = AuthService(
        users=SqlUserRepository(sessions),
        sessions=SqlSessionStore(sessions),
        attempts=SqlLoginAttemptStore(sessions, "test-rate-limit-secret"),
        hasher=Argon2PasswordHasher(),
        issuer=JwtTokenIssuer("s" * 32),
        clock=clock,
        access_ttl=900,
        refresh_ttl=86400,
    )
    auth_reads, auth_commands = auth_bindings(auth_service)
    extra_reads.update({**context_reads, **auth_reads})
    extra_reads["listModels"] = lambda p, q: {}
    extra_reads["getModel"] = lambda p, q: {}
    extra_commands.update({**context_commands, **auth_commands})
    app = create_http_app(
        reads,
        ForecastService(repo, clock, reads),
        contract,
        viewer_token="v" * 32,
        operator_token="o" * 32,
        extra_reads=extra_reads,
        extra_commands=extra_commands,
        auth_service=auth_service,
        model_status=lambda: status,
    )
    return TestClient(app), contract


@pytest.mark.parametrize(
    "bundle,fallback,code,state",
    [
        (INVALID, False, 503, "invalid"),
        (INVALID, True, 200, "fallback"),
        (ok_bundle(), True, 200, "ok"),
    ],
)
def test_health_reports_model_readiness(pipeline, bundle, fallback, code, state):
    client, contract = health_client(pipeline, model_readiness(bundle, fallback))
    with client:
        response = client.get("/api/v1/health")
    assert response.status_code == code
    body = response.json()
    contract.validator(contract.document["components"]["schemas"]["Health"]).validate(body)
    assert body["model"] == state and body["model_version"] == "bundle_v1"
    assert body["status"] == ("ready" if code == 200 else "unavailable")


# --- a real exported baseline bundle -------------------------------------------------


def test_exported_baseline_bundle_forecasts_through_the_worker_predictor(tmp_path):
    grid = generate_full_grid("2025-01-06", "2025-02-02")
    grid["boardings"] = (grid["hour"].between(6, 22) * (grid["route"] != 5) * 100).astype(float)
    profiles = calculate_historical_profiles(add_calendar_features(grid))
    export(tmp_path / "models", profiles=profiles, training_history_end=HISTORY_END)
    predictor = ArtifactPredictor.from_version(tmp_path / "models", "bundle_v1")

    start = pd.Timestamp("2025-11-03T00:00:00", tz=MOSCOW).to_pydatetime()
    window = forecast_window(start, Horizon.DAY, Resolution.HOUR)
    series = tuple(SpatialKey(level=SpatialLevel.ROUTE, route_id=r) for r in ("5", "17"))
    predictions = predictor.predict((), series, window, Horizon.DAY, Resolution.HOUR, start)

    by_route = {r: [p.value for p in predictions if p.spatial.route_id == r] for r in ("5", "17")}
    assert len(by_route["5"]) == len(by_route["17"]) == 24
    assert all(v == 0 for v in by_route["5"])
    assert all(v >= 0 for v in by_route["17"]) and max(by_route["17"]) > 0
