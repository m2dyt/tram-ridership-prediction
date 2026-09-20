import pytest
from tram.domain.errors import DomainError
from tram.domain.fleet import fleet_scenario

from tests.test_api import api as api
from tests.test_api import checked


def command():
    return dict(
        passengers_per_hour=1000,
        vehicle_capacity=100,
        target_ratio=0.8,
        round_trip_minutes=60,
        current_vehicles=10,
        reserve_vehicles=2,
    )


def test_fleet_rounding_and_insufficient_reserve():
    result = fleet_scenario(command())
    assert result["required_vehicles"] == 13
    assert result["maximum_headway_minutes"] == 4.8
    assert result["additional_vehicles"] == 3
    assert result["reserve_shortfall"] == 1
    assert not result["feasible_with_reserve"]


def test_zero_demand_does_not_divide_by_zero():
    result = fleet_scenario({**command(), "passengers_per_hour": 0})
    assert result["required_vehicles"] == 0
    assert result["maximum_headway_minutes"] is None
    with pytest.raises(DomainError):
        fleet_scenario({**command(), "target_ratio": 0})


def test_fleet_api(api):
    checked(api, "POST", "/scenarios/fleet", json=command(), status=403)
    result = checked(api, "POST", "/scenarios/fleet", json=command(), role="operator").json()
    assert result["value_kind"] == "scenario"
