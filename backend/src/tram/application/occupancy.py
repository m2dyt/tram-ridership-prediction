from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Protocol

from tram.application.errors import ApplicationError
from tram.application.ports import Clock, Document
from tram.application.service import required
from tram.domain.occupancy import new_state, visit
from tram.domain.time import MOSCOW, parse_time


class TripStore(Protocol):
    def create(self, document: Document, fingerprint: str) -> Document: ...
    def get(self, trip_id: str) -> Document | None: ...
    def list(self, query: Document, before, offset: int, limit: int) -> list[Document]: ...
    def events(self, trip_id: str) -> list[Document]: ...
    def apply(
        self, trip_id: str, event: Document, fingerprint: str, reducer: Callable
    ) -> Document: ...


def fingerprint(document):
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class OccupancyService:
    def __init__(self, store: TripStore, clock: Clock, reads):
        self.store, self.clock, self.reads = store, clock, reads

    def create(self, command):
        network = self.reads.network(command["network_revision_id"])
        route = required(
            next((r for r in network["routes"] if r["route"]["id"] == command["route_id"]), None),
            "Route",
        )
        direction = required(
            next((d for d in route["directions"] if d["id"] == command["direction_id"]), None),
            "Direction",
        )
        actual = [(s["sequence"], s["stop_id"]) for s in command["stops"]]
        expected = [(s["sequence"], s["stop_id"]) for s in direction["stops"]]
        if actual != expected:
            raise ApplicationError(
                "VALIDATION_ERROR", "Trip must follow every stop visit of the published direction"
            )
        first = parse_time(command["started_at"]).astimezone(MOSCOW).date().isoformat()
        last = parse_time(command["stops"][-1]["arrival_at"]).astimezone(MOSCOW).date().isoformat()
        info = route["route"]
        if first < info["valid_from"] or (info["valid_to"] and last >= info["valid_to"]):
            raise ApplicationError("VALIDATION_ERROR", "Trip falls outside route validity")
        state = new_state(command)
        state.update(
            occupancy_ratio=state["remaining"] / command["capacity"]
            if command["capacity"]
            else None,
            flags=["unverified_duration_assumption"]
            + (
                ["over_capacity"]
                if command["capacity"] and state["remaining"] > command["capacity"]
                else []
            ),
        )
        now = self.clock.now().isoformat()
        document = {
            "id": command["trip_id"],
            "plan": command,
            "state": state,
            "created_at": now,
            "updated_at": now,
        }
        return self.store.create(document, fingerprint(command))

    def get(self, trip_id):
        return required(self.store.get(trip_id), "Occupancy trip")

    def list(self, query):
        items, page = self.reads.paginate(
            "occupancy-trips",
            query,
            lambda offset, limit, before: self.store.list(query, before, offset, limit),
        )
        return {"items": items, "page": page}

    def events(self, trip_id):
        self.get(trip_id)
        return {"items": self.store.events(trip_id)}

    def apply(self, trip_id, event):
        if parse_time(event["available_at"]) > self.clock.now():
            raise ApplicationError(
                "VALIDATION_ERROR", "Future events cannot update the observed trip state"
            )

        def reduce(trip, command):
            return {**visit(trip, command), "updated_at": self.clock.now().isoformat()}

        return self.store.apply(trip_id, event, fingerprint(event), reduce)
