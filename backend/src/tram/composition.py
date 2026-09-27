import logging
from contextlib import contextmanager

from tram_ml.baseline import SeasonalNaive

from tram.application.worker import RunWorker
from tram.infrastructure.database import make_engine, session_factory
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SystemClock
from tram.infrastructure.settings import Settings

LOGGER = logging.getLogger(__name__)


class ModelBundleUnavailable(RuntimeError):
    """A bundle is configured but unusable and fallback to the seasonal baseline is off."""


def create_app():
    from contextlib import asynccontextmanager

    from sqlalchemy.exc import OperationalError
    from sqlalchemy.exc import TimeoutError as PoolTimeout

    from tram.api.app import create_http_app
    from tram.api.extensions import auth_bindings, context_bindings, occupancy_bindings
    from tram.application.auth import AuthService
    from tram.application.models import model_readiness
    from tram.application.occupancy import OccupancyService
    from tram.application.service import ForecastService, ReadService
    from tram.infrastructure.auth import (
        Argon2PasswordHasher,
        JwtTokenIssuer,
        SqlSessionStore,
        SqlUserRepository,
    )
    from tram.infrastructure.contract import Contract
    from tram.infrastructure.login_attempts import SqlLoginAttemptStore
    from tram.infrastructure.ml.model_catalog import FileModelCatalog
    from tram.infrastructure.runtime import SignedCursor
    from tram.infrastructure.trips import SqlTripStore

    settings = Settings()
    settings.require_api_secrets()
    contract = Contract(settings.openapi_path)
    engine = make_engine(settings.database_url.get_secret_value())
    repository = SqlRepository(session_factory(engine))
    clock = SystemClock()
    reads = ReadService(repository, clock, SignedCursor(settings.cursor_secret.get_secret_value()))
    catalog = FileModelCatalog(settings.models_root, settings.model_version)

    auth_service = AuthService(
        users=SqlUserRepository(session_factory(engine)),
        sessions=SqlSessionStore(session_factory(engine)),
        attempts=SqlLoginAttemptStore(
            session_factory(engine), settings.auth_token_secret.get_secret_value()
        ),
        hasher=Argon2PasswordHasher(),
        issuer=JwtTokenIssuer(settings.auth_token_secret.get_secret_value()),
        clock=clock,
        access_ttl=settings.access_token_ttl_seconds,
        refresh_ttl=settings.refresh_token_ttl_seconds,
    )
    extra_reads, extra_commands = occupancy_bindings(
        OccupancyService(SqlTripStore(session_factory(engine)), clock, reads)
    )
    context_reads, context_commands = context_bindings(
        build_context(settings, session_factory(engine), clock, reads)
    )
    auth_reads, auth_commands = auth_bindings(auth_service)
    extra_reads.update(context_reads)
    extra_reads.update(auth_reads)
    from tram.api.models import get_model, list_models

    extra_reads["listModels"] = lambda p, q: list_models(settings.models_root)
    extra_reads["getModel"] = lambda p, q: get_model(settings.models_root, p["model_id"])
    extra_commands.update(context_commands)
    extra_commands.update(auth_commands)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            engine.dispose()

    app = create_http_app(
        reads,
        ForecastService(
            repository,
            clock,
            reads,
            models=catalog,
            fallback_to_seasonal_naive=settings.fallback_to_seasonal_naive,
        ),
        contract,
        viewer_token=settings.viewer_token.get_secret_value()
        if settings.allow_static_tokens and settings.viewer_token
        else "",
        operator_token=settings.operator_token.get_secret_value()
        if settings.allow_static_tokens and settings.operator_token
        else "",
        cors_origins=settings.cors_origins,
        lifespan=lifespan,
        unavailable_errors=(OperationalError, PoolTimeout),
        extra_reads=extra_reads,
        extra_commands=extra_commands,
        auth_service=auth_service,
        model_status=lambda: model_readiness(
            catalog.active_bundle(), settings.fallback_to_seasonal_naive
        ),
    )
    if settings.frontend_dist.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app


def publish_bundle(settings: Settings, directory):
    from tram.application.publication import PublishDataset
    from tram.infrastructure.bundles import read_bundle
    from tram.infrastructure.contract import Contract
    from tram.infrastructure.publication import SqlDatasetWriter

    manifest, records = read_bundle(directory, Contract(settings.openapi_path))
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        created = PublishDataset(SqlDatasetWriter(session_factory(engine)), SystemClock()).execute(
            manifest, records
        )
        return manifest["capabilities"]["dataset_revision_id"], created
    finally:
        engine.dispose()


def build_context(settings, sessions, clock, reads):
    from tram.application.context import ContextService
    from tram.infrastructure.context_store import SqlSnapshotStore
    from tram.infrastructure.sources import ExternalSources

    return ContextService(
        SqlSnapshotStore(sessions),
        ExternalSources(
            settings.weatherapi_key.get_secret_value(), settings.timepad_token.get_secret_value()
        ),
        clock,
        reads,
    )


def worker_predictors(settings: Settings):
    """Predictors keyed by ModelReference.method, plus the bundle description.

    The seasonal baseline is always available: it is the designated model for
    runs pinned to seasonal_naive_v1, not a silent substitute for a bundle.
    """
    from tram.application.models import BUNDLE_METHOD, SEASONAL_METHOD
    from tram.infrastructure.ml.artifact_predictor import ArtifactPredictor
    from tram.infrastructure.ml.model_catalog import FileModelCatalog

    bundle = FileModelCatalog(settings.models_root, settings.model_version).active_bundle()
    predictors = {SEASONAL_METHOD: SeasonalNaive()}
    if bundle["status"] == "ok":
        try:
            predictors[BUNDLE_METHOD] = ArtifactPredictor.from_version(
                settings.models_root, bundle["version"]
            )
        except Exception as exc:  # unpickling, missing libraries, file changed meanwhile
            bundle = {
                **bundle,
                "status": "invalid",
                "reason": f"estimator could not be loaded ({type(exc).__name__})",
            }
    if bundle["status"] == "invalid":
        message = f"Model bundle {bundle['version'] or '(unset)'} is invalid: {bundle['reason']}"
        if not settings.fallback_to_seasonal_naive:
            raise ModelBundleUnavailable(
                message + "; fallback to the seasonal baseline is disabled"
            )
        LOGGER.error("%s; serving seasonal_naive_v1 runs, bundle runs will fail", message)
    elif bundle["status"] == "ok":
        LOGGER.info("Serving model bundle %s", bundle["version"])
    else:
        LOGGER.info("No model bundle configured; serving seasonal_naive_v1 runs")
    return predictors, bundle


@contextmanager
def build_worker(settings: Settings):
    """Compose the worker at the process boundary; always release its DB pool."""
    predictors, _ = worker_predictors(settings)
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        repository = SqlRepository(session_factory(engine))
        yield RunWorker(
            repository,
            SystemClock(),
            predictors,
            lease_seconds=settings.lease_seconds,
            max_attempts=settings.max_attempts,
        )
    finally:
        engine.dispose()
