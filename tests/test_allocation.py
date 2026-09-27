import math

import pytest
from tram.domain.allocation import HUB_BONUS, stop_shares
from tram.domain.errors import DomainError


def test_route_total_is_conserved_and_transfer_stops_weigh_more():
    shares = stop_shares({"1": ["a", "hub", "b"], "7": ["hub", "c"], "11": ["hub"]})
    for route in shares.values():
        assert math.fsum(route) == pytest.approx(1)
    first = shares["1"]
    assert first[1] / first[0] == pytest.approx(1 + 2 * HUB_BONUS)
    assert first[0] == first[2]
    assert shares["11"] == [1.0]


def test_single_route_without_transfers_is_uniform():
    assert stop_shares({"r": ["a", "b", "c", "d"]})["r"] == [0.25] * 4


def test_route_without_stops_is_rejected():
    with pytest.raises(DomainError):
        stop_shares({"5": []})
