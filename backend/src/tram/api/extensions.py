"""Bind additional application services to the contract, without database access."""


def occupancy_bindings(service):
    from tram.domain.fleet import fleet_scenario

    return (
        {
            "listOccupancyTrips": lambda p, q: service.list(q),
            "getOccupancyTrip": lambda p, q: service.get(p["trip_id"]),
            "getOccupancyEvents": lambda p, q: service.events(p["trip_id"]),
        },
        {
            "calculateFleetScenario": lambda p, c: fleet_scenario(c),
            "createOccupancyTrip": lambda p, c: service.create(c),
            "applyOccupancyEvent": lambda p, c: service.apply(p["trip_id"], c),
        },
    )


def context_bindings(service):
    return (
        {
            "listContextSnapshots": lambda p, q: service.list(q),
            "getContextSnapshot": lambda p, q: service.get(p["snapshot_id"]),
        },
        {"refreshContext": lambda p, c: service.refresh(c)},
    )
