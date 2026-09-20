import copy
import hashlib
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from tram.application.errors import ApplicationError
from tram.application.mapping import spatial_from_document
from tram.domain.series import Observation
from tram.domain.time import Interval, add_months, parse_time
from tram.infrastructure.database import (
    DatasetRow,
    EvaluationPointRow,
    EvaluationRow,
    ForecastPointRow,
    NetworkRow,
    ObservationRow,
    RequestKeyRow,
    RunRouteRow,
    RunRow,
    SeriesRow,
)


def point_columns(document):
    spatial = spatial_from_document(document["spatial"])
    return {
        "series_key": spatial.canonical,
        "interval_start": parse_time(document["interval_start"]),
        "interval_end": parse_time(document["interval_end"]),
        **{
            name: getattr(spatial, name)
            for name in ("route_id", "direction_id", "stop_id", "stop_sequence", "segment_id")
        },
        "document": document,
    }


def filtered_points(statement, table, query):
    if query.get("from"):
        statement = statement.where(table.interval_start >= parse_time(query["from"]))
    if query.get("to"):
        statement = statement.where(table.interval_end <= parse_time(query["to"]))
    for name in ("route_id", "direction_id", "stop_id", "stop_sequence", "segment_id"):
        if query.get(name) is not None:
            statement = statement.where(getattr(table, name) == query[name])
    if query.get("interval_start"):
        statement = statement.where(table.interval_start == parse_time(query["interval_start"]))
    return statement.order_by(
        table.interval_start,
        table.route_id,
        table.direction_id.nulls_first(),
        table.stop_sequence.nulls_first(),
        table.stop_id.nulls_first(),
        table.segment_id.nulls_first(),
    )


class SqlRepository:
    def __init__(self, sessions):
        self.sessions = sessions

    def healthy(self):
        try:
            with self.sessions() as session:
                session.execute(select(DatasetRow.id).limit(1))
            return True
        except SQLAlchemyError:
            return False

    def dataset(self, revision):
        with self.sessions() as session:
            row = (
                session.get(DatasetRow, revision)
                if revision
                else session.scalar(
                    select(DatasetRow)
                    .order_by(DatasetRow.published_at.desc(), DatasetRow.id.desc())
                    .limit(1)
                )
            )
            return copy.deepcopy(row.document) if row else None

    def network(self, revision):
        with self.sessions() as session:
            row = session.get(NetworkRow, revision)
            return copy.deepcopy(row.document) if row else None

    def observation_points(self, revision, profile, query, offset, limit):
        statement = select(ObservationRow).where(
            ObservationRow.dataset_id == revision, ObservationRow.profile_id == profile
        )
        with self.sessions() as session:
            return [
                r.document
                for r in session.scalars(
                    filtered_points(statement, ObservationRow, query).offset(offset).limit(limit)
                )
            ]

    @staticmethod
    def _existing(session, owner, key, fingerprint, now):
        row = session.get(RequestKeyRow, (owner, key))
        if row and row.expires_at > now:
            if row.fingerprint != fingerprint:
                raise ApplicationError(
                    "IDEMPOTENCY_CONFLICT", "Idempotency key was used for a different request"
                )
            return session.get(RunRow, row.run_id).document
        return None

    def replay_run(self, owner, key, fingerprint, now):
        with self.sessions() as session:
            return self._existing(session, owner, key, fingerprint, now)

    def create_run(self, owner, key, fingerprint, run, now):
        with self.sessions.begin() as session:
            if session.bind.dialect.name == "postgresql":
                # Serializes exactly this principal/key across API processes.
                lock_key = int.from_bytes(
                    hashlib.sha256(f"{owner}\0{key}".encode()).digest()[:8], signed=True
                )
                session.execute(select(func.pg_advisory_xact_lock(lock_key)))
            existing = self._existing(session, owner, key, fingerprint, now)
            if existing:
                return existing, False
            session.execute(
                delete(RequestKeyRow).where(RequestKeyRow.owner == owner, RequestKeyRow.key == key)
            )
            session.add(
                RunRow(
                    id=run["id"],
                    dataset_id=run["dataset_revision_id"],
                    profile_id=run["profile"]["id"],
                    horizon=run["profile"]["horizon"],
                    status="queued",
                    created_at=now,
                    forecast_start=parse_time(run["forecast_start"]),
                    document=run,
                )
            )
            session.flush()
            session.add_all(
                RunRouteRow(run_id=run["id"], route_id=route) for route in run["route_ids"]
            )
            session.add(
                RequestKeyRow(
                    owner=owner,
                    key=key,
                    fingerprint=fingerprint,
                    run_id=run["id"],
                    expires_at=now + timedelta(hours=24),
                )
            )
            return copy.deepcopy(run), True

    def run(self, run_id):
        with self.sessions() as session:
            row = session.get(RunRow, run_id)
            return copy.deepcopy(row.document) if row else None

    def runs(self, query, before, offset, limit):
        statement = select(RunRow).where(RunRow.created_at <= before)
        for name, column in (
            ("dataset_revision_id", "dataset_id"),
            ("profile_id", "profile_id"),
            ("horizon", "horizon"),
        ):
            if query.get(name):
                statement = statement.where(getattr(RunRow, column) == query[name])
        # Membership uses the status at the first page's timestamp; documents stay live.
        # State is monotonic: queued -> running -> succeeded/failed (retries keep running).
        if query.get("status") == "queued":
            statement = statement.where(
                or_(RunRow.started_at.is_(None), RunRow.started_at > before)
            )
        elif query.get("status") == "running":
            statement = statement.where(
                RunRow.started_at <= before,
                or_(RunRow.finished_at.is_(None), RunRow.finished_at > before),
            )
        elif query.get("status") in ("succeeded", "failed"):
            statement = statement.where(
                RunRow.status == query["status"], RunRow.finished_at <= before
            )
        if query.get("forecast_start"):
            statement = statement.where(
                RunRow.forecast_start == parse_time(query["forecast_start"])
            )
        if query.get("route_id"):
            statement = statement.where(
                select(RunRouteRow.run_id)
                .where(RunRouteRow.run_id == RunRow.id, RunRouteRow.route_id == query["route_id"])
                .exists()
            )
        with self.sessions() as session:
            return [
                row.document
                for row in session.scalars(
                    statement.order_by(RunRow.created_at.desc(), RunRow.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ]

    def forecast_points(self, run_id, query, offset, limit):
        statement = select(ForecastPointRow).where(ForecastPointRow.run_id == run_id)
        with self.sessions() as session:
            return [
                row.document
                for row in session.scalars(
                    filtered_points(statement, ForecastPointRow, query).offset(offset).limit(limit)
                )
            ]

    def series(self, revision, profile, route_ids):
        with self.sessions() as session:
            return [
                row.document
                for row in session.scalars(
                    select(SeriesRow)
                    .where(
                        SeriesRow.dataset_id == revision,
                        SeriesRow.profile_id == profile,
                        SeriesRow.route_id.in_(route_ids),
                    )
                    .order_by(SeriesRow.series_key)
                )
            ]

    def history(self, revision, profile, spatial, as_of):
        # At most two years for one aggregate series, never all raw source records.
        with self.sessions() as session:
            rows = session.scalars(
                select(ObservationRow)
                .where(
                    ObservationRow.dataset_id == revision,
                    ObservationRow.profile_id == profile,
                    ObservationRow.series_key == spatial.canonical,
                    ObservationRow.interval_start >= add_months(as_of, -24),
                    ObservationRow.interval_end <= as_of,
                    ObservationRow.available_at <= as_of,
                )
                .order_by(ObservationRow.interval_start)
            )
            return tuple(
                Observation(
                    spatial,
                    Interval(row.interval_start, row.interval_end),
                    row.available_at,
                    row.document["value"],
                )
                for row in rows
            )

    def claim(self, now, lease_seconds, max_attempts):
        with self.sessions.begin() as session:
            statement = (
                select(RunRow)
                .where(
                    or_(
                        RunRow.status == "queued",
                        and_(RunRow.status == "running", RunRow.lease_until <= now),
                    )
                )
                .order_by(RunRow.created_at, RunRow.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            for row in session.scalars(statement):
                if row.attempts >= max_attempts:
                    row.status = "failed"
                    row.finished_at = now
                    row.document = {
                        **row.document,
                        "status": "failed",
                        "finished_at": now.isoformat(),
                        "failure": {
                            "code": "ATTEMPTS_EXHAUSTED",
                            "message": "Worker lease expired too many times",
                            "retryable": False,
                        },
                    }
                    row.lease_until = None
                    row.lease_token = None
                    continue
                token = str(uuid4())
                row.status, row.lease_token = "running", token
                row.started_at = row.started_at or now
                row.lease_until = now + timedelta(seconds=lease_seconds)
                row.attempts += 1
                row.document = {
                    **row.document,
                    "status": "running",
                    "started_at": row.document["started_at"] or now.isoformat(),
                }
                return {"run": copy.deepcopy(row.document), "lease_token": token}
        return None

    def heartbeat(self, run_id, token, now, lease_seconds):
        with self.sessions.begin() as session:
            result = session.execute(
                update(RunRow)
                .where(
                    RunRow.id == run_id,
                    RunRow.lease_token == token,
                    RunRow.status == "running",
                    RunRow.lease_until > now,
                )
                .values(lease_until=now + timedelta(seconds=lease_seconds))
            )
            return result.rowcount == 1

    def complete(self, run_id, token, points, now):
        with self.sessions.begin() as session:
            row = session.scalar(select(RunRow).where(RunRow.id == run_id).with_for_update())
            if (
                not row
                or row.status != "running"
                or row.lease_token != token
                or row.lease_until <= now
            ):
                return False
            for point in points:
                session.add(ForecastPointRow(run_id=run_id, **point_columns(point)))
            missing = sum(point["value"] is None for point in points)
            row.status = "succeeded"
            row.finished_at = now
            row.lease_until, row.lease_token = None, None
            quality = {
                "status": "partial" if missing else "ok",
                "coverage_ratio": (len(points) - missing) / len(points) if points else None,
                "flags": ["missing_references"] if missing else [],
            }
            row.document = {
                **row.document,
                "status": "succeeded",
                "calculated_at": now.isoformat(),
                "finished_at": now.isoformat(),
                "point_count": len(points),
                "quality": quality,
            }
            return True

    def fail(self, run_id, token, now, code, message):
        with self.sessions.begin() as session:
            row = session.scalar(select(RunRow).where(RunRow.id == run_id).with_for_update())
            if (
                not row
                or row.status != "running"
                or row.lease_token != token
                or row.lease_until <= now
            ):
                return False
            row.status = "failed"
            row.finished_at = now
            row.lease_until, row.lease_token = None, None
            row.document = {
                **row.document,
                "status": "failed",
                "finished_at": now.isoformat(),
                "failure": {"code": code, "message": message, "retryable": False},
            }
            return True

    def evaluation(self, evaluation_id):
        with self.sessions() as session:
            row = session.get(EvaluationRow, evaluation_id)
            return row.document if row else None

    def evaluations(self, query, before, offset, limit):
        statement = select(EvaluationRow).where(EvaluationRow.created_at <= before)
        for name, column in (
            ("dataset_revision_id", "dataset_id"),
            ("profile_id", "profile_id"),
            ("status", "status"),
            ("horizon", "horizon"),
            ("model_id", "model_id"),
        ):
            if query.get(name):
                statement = statement.where(getattr(EvaluationRow, column) == query[name])
        with self.sessions() as session:
            return [
                row.document["summary"]
                for row in session.scalars(
                    statement.order_by(EvaluationRow.created_at.desc(), EvaluationRow.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ]

    def evaluation_points(self, evaluation_id, query, offset, limit):
        statement = select(EvaluationPointRow).where(
            EvaluationPointRow.evaluation_id == evaluation_id
        )
        if query.get("fold_id"):
            statement = statement.where(EvaluationPointRow.fold_id == query["fold_id"])
        if query.get("demand_slice") == "peak":
            statement = statement.where(EvaluationPointRow.document["is_peak"].as_boolean())
        statement = filtered_points(
            statement.order_by(EvaluationPointRow.fold_id), EvaluationPointRow, query
        )
        with self.sessions() as session:
            return [row.document for row in session.scalars(statement.offset(offset).limit(limit))]
