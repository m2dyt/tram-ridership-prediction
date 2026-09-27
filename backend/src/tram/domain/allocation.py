"""Estimated split of route totals over stops; the source never records the stop.

Validations identify the route (``ngpt_route``), not the boarding stop, so a stop-level
series can only be an estimate. Each route value is shared over the route's stop
positions: every position gets a base weight of 1, and a stop that other published
routes also serve gets ``HUB_BONUS`` extra per additional route (a transfer node
attracts more boardings). Shares of one route sum to 1, so stop values always add up
to the route total they came from. Values built this way must be labelled
``value_kind="estimated"`` with ``ESTIMATION_METHOD``.
"""

import math
from collections import Counter

from tram.domain.errors import DomainError

ESTIMATION_METHOD = "route_total_stop_share_v1"
HUB_BONUS = 0.5


def stop_shares(route_stops: dict[str, list[str]]) -> dict[str, list[float]]:
    """Share of each stop position (in list order) of every route's total."""
    served = Counter(stop for stops in route_stops.values() for stop in set(stops))
    result = {}
    for route, stops in route_stops.items():
        if not stops:
            raise DomainError(f"Route {route} has no stops to share its total over")
        weights = [1 + HUB_BONUS * (served[stop] - 1) for stop in stops]
        total = math.fsum(weights)
        result[route] = [weight / total for weight in weights]
    return result
