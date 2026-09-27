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
            "getContextSnapshotGeojson": lambda p, q: service.geojson(p["snapshot_id"]),
        },
        {"refreshContext": lambda p, c: service.refresh(c)},
    )


def auth_bindings(service):
    def login(p, c, request):
        client_ip = request.client.host if request.client else "unknown"
        access, access_exp, refresh, user = service.login(c["username"], c["password"], client_ip)
        from fastapi.responses import JSONResponse

        response = JSONResponse(
            {
                "access_token": access,
                "token_type": "Bearer",
                "expires_in": int(access_exp.timestamp() - service.clock.now().timestamp()),
                "role": user["role"],
                "user": {"id": user["id"], "username": user["username"]},
            }
        )
        response.set_cookie(
            "tram_refresh",
            refresh,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/api/v1/auth",
        )
        return response

    def refresh(p, c, request):
        token = request.cookies.get("tram_refresh")
        if not token:
            from tram.application.errors import ApplicationError

            raise ApplicationError("UNAUTHORIZED", "Missing refresh token")
        access, access_exp, new_refresh = service.refresh(token)
        from fastapi.responses import JSONResponse

        response = JSONResponse(
            {
                "access_token": access,
                "token_type": "Bearer",
                "expires_in": int(access_exp.timestamp() - service.clock.now().timestamp()),
                # Wait, refresh also returns role? Oh, we don't have it easily without user doc. Let's return just access token details, or modify service.refresh to return role.
            }
        )
        response.set_cookie(
            "tram_refresh",
            new_refresh,
            httponly=True,
            secure=True,
            samesite="strict",
            path="/api/v1/auth",
        )
        return response

    def logout(p, c, request):
        token = request.cookies.get("tram_refresh")
        service.logout(token, c.get("everywhere", False) if c else False)
        from fastapi.responses import Response

        response = Response(status_code=204)
        response.delete_cookie("tram_refresh", path="/api/v1/auth")
        return response

    def me(p, q, request):
        # user info is extracted in authorize() and put into request.state.user
        return service.me(request.state.user["user_id"])

    # Notice that we need access to `request` for cookies. The `commands` dict in app.py currently calls:
    # commands[operation["operationId"]](request.path_params, command)
    # We will need to adapt app.py to pass request.
    return (
        {
            "authMe": lambda p, q, r: me(p, q, r),
            "authRefresh": lambda p, q, r: refresh(p, q, r),
        },
        {
            "authRegister": lambda p, c, r: service.register(c["username"], c["password"]),
            "authCreateOperator": lambda p, c, r: service.create_operator(
                c["username"], c["password"]
            ),
            "authLogin": lambda p, c, r: login(p, c, r),
            "authLogout": lambda p, c, r: logout(p, c, r),
        },
    )
