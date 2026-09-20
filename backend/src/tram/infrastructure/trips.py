import copy
import hashlib

from sqlalchemy import func, select

from tram.application.errors import ApplicationError
from tram.domain.time import parse_time
from tram.infrastructure.database import TripEventRow, TripRow


class SqlTripStore:
    def __init__(self, sessions):
        self.sessions = sessions

    @staticmethod
    def lock(session, trip_id):
        if session.bind.dialect.name == "postgresql":
            key = int.from_bytes(
                hashlib.sha256(("occupancy:" + trip_id).encode()).digest()[:8], signed=True
            )
            session.execute(select(func.pg_advisory_xact_lock(key)))

    def create(self, document, fingerprint):
        with self.sessions.begin() as session:
            self.lock(session, document["id"])
            existing = session.get(TripRow, document["id"])
            if existing:
                if existing.fingerprint != fingerprint:
                    raise ApplicationError(
                        "IDEMPOTENCY_CONFLICT", "Trip ID belongs to a different plan"
                    )
                return copy.deepcopy(existing.document)
            session.add(
                TripRow(
                    id=document["id"],
                    network_id=document["plan"]["network_revision_id"],
                    vehicle_id=document["plan"]["vehicle_id"],
                    created_at=parse_time(document["created_at"]),
                    fingerprint=fingerprint,
                    document=document,
                )
            )
            return document

    def get(self, trip_id):
        with self.sessions() as session:
            row = session.get(TripRow, trip_id)
            return copy.deepcopy(row.document) if row else None

    def list(self, query, before, offset, limit):
        statement = select(TripRow).where(TripRow.created_at <= before)
        if query.get("vehicle_id"):
            statement = statement.where(TripRow.vehicle_id == query["vehicle_id"])
        with self.sessions() as session:
            return [
                r.document
                for r in session.scalars(
                    statement.order_by(TripRow.created_at.desc(), TripRow.id)
                    .offset(offset)
                    .limit(limit)
                )
            ]

    def events(self, trip_id):
        with self.sessions() as session:
            return [
                r.document
                for r in session.scalars(
                    select(TripEventRow)
                    .where(TripEventRow.trip_id == trip_id)
                    .order_by(TripEventRow.sequence)
                )
            ]

    def apply(self, trip_id, event, fingerprint, reducer):
        with self.sessions.begin() as session:
            self.lock(session, trip_id)
            row = session.get(TripRow, trip_id)
            if row is None:
                raise ApplicationError("NOT_FOUND", "Occupancy trip not found")
            previous = session.get(TripEventRow, (trip_id, event["event_id"]))
            if previous:
                if previous.fingerprint != fingerprint:
                    raise ApplicationError(
                        "IDEMPOTENCY_CONFLICT", "Event ID belongs to different data"
                    )
                return copy.deepcopy(row.document)
            result = reducer(copy.deepcopy(row.document), event)
            row.document = result
            # Every event stores a durable checkpoint and the original command in one transaction.
            session.add(
                TripEventRow(
                    trip_id=trip_id,
                    event_id=event["event_id"],
                    sequence=event["sequence"],
                    fingerprint=fingerprint,
                    document={"event": event, "state_after": result["state"]},
                )
            )
            return result
