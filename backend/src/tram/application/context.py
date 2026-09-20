"""Capture immutable external context; unavailable providers never become synthetic data."""

from typing import Protocol
from uuid import uuid4

from tram.application.errors import ApplicationError
from tram.application.ports import Document
from tram.application.service import required
from tram.domain.time import parse_time


class ContextProvider(Protocol):
    def fetch(self, command: Document) -> Document: ...


class SnapshotStore(Protocol):
    def save(self, document: Document) -> None: ...
    def get(self, snapshot_id: str) -> Document | None: ...
    def select(self, query: Document, before, offset: int, limit: int) -> list[Document]: ...


class ContextService:
    def __init__(self, store: SnapshotStore, provider: ContextProvider, clock, reads):
        self.store, self.provider, self.clock, self.reads = store, provider, clock, reads

    def capture(self, provider, payload, request=None):
        # Availability is completion of retrieval, not the future time being forecast.
        now = self.clock.now().isoformat()
        document = {
            "id": str(uuid4()),
            "provider": provider,
            "created_at": now,
            "available_at": now,
            "request": request or {},
            **payload,
        }
        self.store.save(document)
        return document

    def refresh(self, command):
        delta = parse_time(command["to"]) - parse_time(command["from"])
        if not 0 < delta.total_seconds() <= 7 * 86400:
            raise ApplicationError(
                "VALIDATION_ERROR", "Context window must be positive and at most 7 days"
            )
        payload = self.provider.fetch(command)
        return self.capture(command["provider"], payload, command)

    def get(self, snapshot_id):
        return required(self.store.get(snapshot_id), "Context snapshot")

    def list(self, query):
        items, page = self.reads.paginate(
            "context-snapshots",
            query,
            lambda offset, limit, before: self.store.select(query, before, offset, limit),
        )
        return {
            "items": [{k: v for k, v in item.items() if k != "records"} for item in items],
            "page": page,
        }
