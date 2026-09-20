from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


class Timestamp(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Database timestamps must be timezone aware")
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        # SQLite strips timezone info; its test adapter stores UTC exclusively.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class NetworkRow(Base):
    __tablename__ = "network_revisions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document: Mapped[dict] = mapped_column(JSON_TYPE)


class DatasetRow(Base):
    __tablename__ = "dataset_revisions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    network_id: Mapped[str] = mapped_column(ForeignKey("network_revisions.id"))
    published_at: Mapped[datetime] = mapped_column(Timestamp(), index=True)
    manifest_hash: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict] = mapped_column(JSON_TYPE)


class SeriesRow(Base):
    __tablename__ = "series"
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_revisions.id"), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    series_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(128), index=True)
    document: Mapped[dict] = mapped_column(JSON_TYPE)


class ObservationRow(Base):
    __tablename__ = "observations"
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_revisions.id"), primary_key=True)
    profile_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    series_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    interval_start: Mapped[datetime] = mapped_column(Timestamp(), primary_key=True)
    interval_end: Mapped[datetime] = mapped_column(Timestamp())
    available_at: Mapped[datetime] = mapped_column(Timestamp())
    route_id: Mapped[str] = mapped_column(String(128))
    direction_id: Mapped[str | None] = mapped_column(String(128))
    stop_id: Mapped[str | None] = mapped_column(String(128))
    stop_sequence: Mapped[int | None] = mapped_column(Integer)
    segment_id: Mapped[str | None] = mapped_column(String(128))
    document: Mapped[dict] = mapped_column(JSON_TYPE)
    __table_args__ = (
        ForeignKeyConstraint(
            ["dataset_id", "profile_id", "series_key"],
            ["series.dataset_id", "series.profile_id", "series.series_key"],
        ),
        CheckConstraint("interval_start < interval_end", name="observation_interval"),
        CheckConstraint("available_at >= interval_end", name="observation_availability"),
        Index("ix_observation_selection", "dataset_id", "profile_id", "interval_start", "route_id"),
    )


class RunRow(Base):
    __tablename__ = "forecast_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_revisions.id"), index=True)
    profile_id: Mapped[str] = mapped_column(String(128))
    horizon: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(Timestamp())
    finished_at: Mapped[datetime | None] = mapped_column(Timestamp())
    forecast_start: Mapped[datetime] = mapped_column(Timestamp())
    lease_until: Mapped[datetime | None] = mapped_column(Timestamp())
    lease_token: Mapped[str | None] = mapped_column(String(36))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    document: Mapped[dict] = mapped_column(JSON_TYPE)
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','succeeded','failed')", name="run_status"),
    )


class RequestKeyRow(Base):
    __tablename__ = "idempotency_keys"
    owner: Mapped[str] = mapped_column(String(128), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(ForeignKey("forecast_runs.id"))
    expires_at: Mapped[datetime] = mapped_column(Timestamp(), index=True)


class RunRouteRow(Base):
    __tablename__ = "forecast_run_routes"
    run_id: Mapped[str] = mapped_column(ForeignKey("forecast_runs.id"), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(128), primary_key=True)


class ForecastPointRow(Base):
    __tablename__ = "forecast_points"
    run_id: Mapped[str] = mapped_column(ForeignKey("forecast_runs.id"), primary_key=True)
    series_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    interval_start: Mapped[datetime] = mapped_column(Timestamp(), primary_key=True)
    interval_end: Mapped[datetime] = mapped_column(Timestamp())
    route_id: Mapped[str] = mapped_column(String(128))
    direction_id: Mapped[str | None] = mapped_column(String(128))
    stop_id: Mapped[str | None] = mapped_column(String(128))
    stop_sequence: Mapped[int | None] = mapped_column(Integer)
    segment_id: Mapped[str | None] = mapped_column(String(128))
    document: Mapped[dict] = mapped_column(JSON_TYPE)
    __table_args__ = (
        CheckConstraint("interval_start < interval_end", name="forecast_interval"),
        Index("ix_forecast_selection", "run_id", "interval_start", "route_id"),
    )


class EvaluationRow(Base):
    __tablename__ = "evaluation_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_revisions.id"), index=True)
    profile_id: Mapped[str] = mapped_column(String(128))
    horizon: Mapped[str] = mapped_column(String(16))
    model_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(Timestamp(), index=True)
    document: Mapped[dict] = mapped_column(JSON_TYPE)


class EvaluationPointRow(Base):
    __tablename__ = "evaluation_points"
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_reports.id"), primary_key=True
    )
    fold_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    series_key: Mapped[str] = mapped_column(String(1024), primary_key=True)
    interval_start: Mapped[datetime] = mapped_column(Timestamp(), primary_key=True)
    interval_end: Mapped[datetime] = mapped_column(Timestamp())
    route_id: Mapped[str] = mapped_column(String(128))
    direction_id: Mapped[str | None] = mapped_column(String(128))
    stop_id: Mapped[str | None] = mapped_column(String(128))
    stop_sequence: Mapped[int | None] = mapped_column(Integer)
    segment_id: Mapped[str | None] = mapped_column(String(128))
    document: Mapped[dict] = mapped_column(JSON_TYPE)


class TripRow(Base):
    __tablename__ = "occupancy_trips"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    network_id: Mapped[str] = mapped_column(ForeignKey("network_revisions.id"))
    vehicle_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp(), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict] = mapped_column(JSON_TYPE)


class TripEventRow(Base):
    __tablename__ = "occupancy_events"
    trip_id: Mapped[str] = mapped_column(ForeignKey("occupancy_trips.id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    document: Mapped[dict] = mapped_column(JSON_TYPE)
    __table_args__ = (UniqueConstraint("trip_id", "sequence", name="uq_trip_stop_visit"),)


class SourceSnapshotRow(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(Timestamp(), index=True)
    document: Mapped[dict] = mapped_column(JSON_TYPE)


def make_engine(url: str):
    options = (
        {"connect_args": {"check_same_thread": False}}
        if url.startswith("sqlite")
        else {"connect_args": {"connect_timeout": 5, "options": "-c statement_timeout=10000"}}
    )
    if url.endswith(":memory:"):
        options["poolclass"] = StaticPool
    engine = create_engine(url, pool_pre_ping=True, **options)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, connection_record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)
