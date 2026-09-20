from sqlalchemy import select

from tram.domain.time import parse_time
from tram.infrastructure.database import SourceSnapshotRow


class SqlSnapshotStore:
    def __init__(self, sessions):
        self.sessions = sessions

    def save(self, document):
        with self.sessions.begin() as session:
            session.add(
                SourceSnapshotRow(
                    id=document["id"],
                    provider=document["provider"],
                    kind=document["kind"],
                    created_at=parse_time(document["created_at"]),
                    document=document,
                )
            )

    def get(self, snapshot_id):
        with self.sessions() as session:
            row = session.get(SourceSnapshotRow, snapshot_id)
            return row.document if row else None

    def select(self, query, before, offset, limit):
        statement = select(SourceSnapshotRow).where(SourceSnapshotRow.created_at <= before)
        for key in ("provider", "kind"):
            if query.get(key):
                statement = statement.where(getattr(SourceSnapshotRow, key) == query[key])
        with self.sessions() as session:
            return [
                r.document
                for r in session.scalars(
                    statement.order_by(SourceSnapshotRow.created_at.desc(), SourceSnapshotRow.id)
                    .offset(offset)
                    .limit(limit)
                )
            ]
