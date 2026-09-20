import copy

import pytest
from tram.domain.errors import DomainError
from tram.domain.occupancy import new_state, visit
from tram.infrastructure.database import NetworkRow

from tests.test_api import api as api
from tests.test_api import checked  # shared HTTP fixture


def plan(strategy="uniform"):
    return {
        "trip_id": "trip-test",
        "vehicle_id": "vehicle-test",
        "network_revision_id": "trip-network",
        "route_id": "demo-route-01",
        "direction_id": "demo-outbound",
        "source_mode": "demo",
        "started_at": "2026-09-20T10:00:00+03:00",
        "strategy": strategy,
        "capacity": 10,
        "initial_passengers": 0,
        "terminal_clear": True,
        "stops": [
            {
                "sequence": i,
                "stop_id": f"stop-{i}",
                "arrival_at": f"2026-09-20T10:{i * 10:02}:00+03:00",
            }
            for i in range(1, 5)
        ],
    }


def event(i, boardings=0, **kwargs):
    at = f"2026-09-20T10:{i * 10:02}:00+03:00"
    return {
        "event_id": f"event-{i}",
        "sequence": i,
        "occurred_at": at,
        "available_at": at,
        "boardings": boardings,
        **kwargs,
    }


@pytest.mark.parametrize(
    "strategy,expected",
    [("short", [12, 0, 0, 0]), ("uniform", [12, 9, 3, 0]), ("long", [12, 12, 12, 0])],
)
def test_cohort_balance(strategy, expected):
    command = plan(strategy)
    trip = {"plan": command, "state": new_state(command)}
    original = copy.deepcopy(trip)
    for i, remainder in enumerate(expected, 1):
        trip = visit(trip, event(i, 12 if i == 1 else 0))
        state = trip["state"]
        assert state["remaining"] == pytest.approx(remainder)
        assert state["remaining"] == pytest.approx(
            state["total_boardings"] - state["total_alightings"]
        )
    assert original["state"]["version"] == 0
    assert trip["state"]["status"] == "completed"


def test_observed_exits_reconcile_cohorts_and_invalid_event_does_not_mutate():
    command = plan("short")
    trip = visit({"plan": command, "state": new_state(command)}, event(1, 12))
    before = copy.deepcopy(trip)
    with pytest.raises(DomainError):
        visit(trip, event(2, observed_alightings=13))
    assert trip == before
    trip = visit(trip, event(2, 2, observed_alightings=4))
    assert trip["state"]["remaining"] == 10
    trip = visit(trip, event(3))
    assert trip["state"]["remaining"] == 0


def seed_trip_network(sessions):
    with sessions.begin() as session:
        base = copy.deepcopy(session.get(NetworkRow, "demo-network-v1").document)
        base["id"] = "trip-network"
        route = base["routes"][0]
        route["stops"] = [
            {"id": f"stop-{i}", "name": str(i), "geometry": None} for i in range(1, 5)
        ]
        route["directions"][0]["stops"] = [
            {"stop_id": f"stop-{i}", "sequence": i} for i in range(1, 5)
        ]
        session.add(NetworkRow(id="trip-network", document=base))


def test_trip_api_replay_and_recovery(api):
    seed_trip_network(api[2].repository.sessions)
    checked(api, "POST", "/occupancy-trips", json=plan(), status=403)
    checked(api, "POST", "/occupancy-trips", json=plan(), role="operator")
    path = "/occupancy-trips/trip-test"
    first = checked(api, "POST", path + "/events", json=event(1, 12), role="operator").json()
    assert first["state"]["occupancy_ratio"] == 1.2
    assert "over_capacity" in first["state"]["flags"]
    assert (
        checked(api, "POST", path + "/events", json=event(1, 12), role="operator").json() == first
    )
    checked(api, "POST", path + "/events", json=event(1, 9), role="operator", status=409)
    checked(api, "POST", path + "/events", json=event(3), role="operator", status=422)
    for i in (2, 3, 4):
        checked(api, "POST", path + "/events", json=event(i), role="operator")
    assert checked(api, "GET", path).json()["state"]["remaining"] == 0
    assert len(checked(api, "GET", path + "/events").json()["items"]) == 4
    checked(api, "GET", "/occupancy-trips")
