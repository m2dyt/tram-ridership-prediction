from contextlib import contextmanager

from tram_ml.baseline import SeasonalNaive

from tram.application.worker import RunWorker
from tram.infrastructure.database import make_engine, session_factory
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SystemClock
from tram.infrastructure.settings import Settings


def create_app():
    from contextlib import asynccontextmanager

    from sqlalchemy.exc import OperationalError
    from sqlalchemy.exc import TimeoutError as PoolTimeout

    from tram.api.app import create_http_app
    from tram.api.extensions import auth_bindings, context_bindings, occupancy_bindings
    from tram.application.auth import AuthService
    from tram.application.occupancy import OccupancyService
    from tram.application.service import ForecastService, ReadService
    from tram.infrastructure.auth import Argon2PasswordHasher, JwtTokenIssuer, SqlSessionStore, SqlUserRepository
    from tram.infrastructure.contract import Contract
    from tram.infrastructure.runtime import SignedCursor
    from tram.infrastructure.trips import SqlTripStore

    settings = Settings()
    settings.require_api_secrets()
    contract = Contract(settings.openapi_path)
    engine = make_engine(settings.database_url.get_secret_value())
    repository = SqlRepository(session_factory(engine))
    clock = SystemClock()
    reads = ReadService(repository, clock, SignedCursor(settings.cursor_secret.get_secret_value()))
    
    auth_service = AuthService(
        users=SqlUserRepository(session_factory(engine)),
        sessions=SqlSessionStore(session_factory(engine)),
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
        ForecastService(repository, clock, reads),
        contract,
        viewer_token=settings.viewer_token.get_secret_value() if settings.allow_static_tokens and settings.viewer_token else "",
        operator_token=settings.operator_token.get_secret_value() if settings.allow_static_tokens and settings.operator_token else "",
        cors_origins=settings.cors_origins,
        lifespan=lifespan,
        unavailable_errors=(OperationalError, PoolTimeout),
        extra_reads=extra_reads,
        extra_commands=extra_commands,
        auth_service=auth_service,
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


@contextmanager
def build_worker(settings: Settings):
    """Compose the worker at the process boundary; always release its DB pool."""
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        repository = SqlRepository(session_factory(engine))
        yield RunWorker(
            repository,
            SystemClock(),
            SeasonalNaive(),
            lease_seconds=settings.lease_seconds,
            max_attempts=settings.max_attempts,
        )
    finally:
        engine.dispose()
