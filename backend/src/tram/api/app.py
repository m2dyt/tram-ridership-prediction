"""HTTP adapter. Route handlers delegate business decisions to application services."""

import hmac
import logging
import re
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jsonschema.exceptions import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from tram.application.errors import ApplicationError
from tram.domain.errors import DomainError

LOGGER = logging.getLogger(__name__)
ERROR_STATUS = {
    "BAD_REQUEST": 400,
    "INVALID_CURSOR": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "UNSUPPORTED_PROFILE": 422,
    "INSUFFICIENT_HISTORY": 422,
    "MODEL_UNAVAILABLE": 422,
    "RESULT_NOT_READY": 409,
    "RUN_FAILED": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "RATE_LIMITED": 429,
    "SERVICE_UNAVAILABLE": 503,
    "INTERNAL_ERROR": 500,
}


def create_http_app(
    reads,
    forecasts,
    contract,
    *,
    viewer_token,
    operator_token,
    cors_origins=(),
    lifespan=None,
    unavailable_errors=(),
    extra_reads=None,
    extra_commands=None,
):
    app = FastAPI(title=contract.document["info"]["title"], lifespan=lifespan)
    app.openapi = lambda: contract.document
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Location", "Retry-After"],
    )

    def error_response(request, code, message, field=None, status=None):
        headers = {"X-Request-ID": request.state.request_id}
        if code == "UNAUTHORIZED":
            headers["WWW-Authenticate"] = "Bearer"
        if code == "SERVICE_UNAVAILABLE":
            headers["Retry-After"] = "5"
        return JSONResponse(
            {
                "code": code,
                "message": message,
                "request_id": request.state.request_id,
                "details": [{"field": field, "reason": message}] if field else [],
            },
            status_code=status or ERROR_STATUS[code],
            headers=headers,
        )

    @app.middleware("http")
    async def request_context(request, call_next):
        request.state.request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception as exc:
            # SQL exceptions may embed credentials or data: log a safe correlation only.
            LOGGER.error("request_id=%s exception=%s", request.state.request_id, type(exc).__name__)
            response = error_response(request, "INTERNAL_ERROR", "Internal server error")
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApplicationError)
    async def application_error(request, exc):
        return error_response(request, exc.code, exc.message, exc.field)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return error_response(request, "VALIDATION_ERROR", str(exc))

    async def unavailable_error(request, exc):
        LOGGER.warning("request_id=%s dependency=%s", request.state.request_id, type(exc).__name__)
        return error_response(request, "SERVICE_UNAVAILABLE", "Database is temporarily unavailable")

    for error_type in unavailable_errors:
        app.add_exception_handler(error_type, unavailable_error)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        code = "NOT_FOUND" if exc.status_code == 404 else "BAD_REQUEST"
        return error_response(request, code, str(exc.detail), status=exc.status_code)

    def authorize(request, operation):
        if operation.get("security") == []:
            return
        values = request.headers.getlist("authorization")
        if len(values) != 1:
            raise ApplicationError("UNAUTHORIZED", "Bearer token is required")
        parts = values[0].split()
        token = parts[1].encode() if len(parts) == 2 and parts[0].lower() == "bearer" else b""
        operator = hmac.compare_digest(token, operator_token.encode())
        viewer = hmac.compare_digest(token, viewer_token.encode())
        if not (operator or viewer):
            raise ApplicationError("UNAUTHORIZED", "Invalid bearer token")
        if request.method == "POST" and not operator:
            raise ApplicationError("FORBIDDEN", "Operator role is required")

    def parameters(request, operation):
        query, headers = {}, {}
        declared = [contract.resolve(p) for p in operation.get("parameters", [])]
        known = {p["name"] for p in declared if p["in"] == "query"}
        if set(request.query_params) - known:
            raise ApplicationError("VALIDATION_ERROR", "Unknown query parameter")
        for parameter in declared:
            name, location, schema = parameter["name"], parameter["in"], parameter["schema"]
            source = {
                "query": request.query_params,
                "header": request.headers,
                "path": request.path_params,
            }[location]
            if hasattr(source, "getlist") and len(source.getlist(name)) > 1:
                raise ApplicationError("VALIDATION_ERROR", "Parameter must occur once", name)
            value = source.get(name, schema.get("default"))
            if value is None:
                if parameter.get("required"):
                    raise ApplicationError(
                        "VALIDATION_ERROR", "Required parameter is missing", name
                    )
                continue
            if schema.get("type") == "integer" and isinstance(value, str):
                if not re.fullmatch(r"-?\d{1,12}", value):
                    raise ApplicationError("VALIDATION_ERROR", "Expected an integer", name)
                value = int(value)
            if next(contract.validator(schema).iter_errors(value), None):
                raise ApplicationError(
                    "VALIDATION_ERROR", "Parameter does not match the API contract", name
                )
            if location == "query":
                query[name] = value
            elif location == "header":
                headers[name] = value
        return query, headers

    def health():
        healthy = reads.repository.healthy()
        return JSONResponse(
            {
                "status": "ready" if healthy else "unavailable",
                "checked_at": reads.clock.now().isoformat(),
                "api_version": "v1",
                "database": "up" if healthy else "down",
            },
            status_code=200 if healthy else 503,
        )

    handlers = {
        "getHealth": lambda p, q: health(),
        "getCapabilities": lambda p, q: reads.capabilities(q),
        "getDataStatus": lambda p, q: reads.data_status(),
        "listRoutes": lambda p, q: reads.routes(q),
        "getRoute": lambda p, q: reads.route(p["route_id"], q),
        "listStops": lambda p, q: reads.stops(q),
        "getObservations": lambda p, q: reads.observations(q),
        "listForecastRuns": lambda p, q: reads.runs(q),
        "getForecastRun": lambda p, q: reads.get_run(p["run_id"]),
        "getForecastPoints": lambda p, q: reads.points(p["run_id"], q),
        "getForecastMap": lambda p, q: JSONResponse(
            reads.map(p["run_id"], q), media_type="application/geo+json"
        ),
        "listEvaluations": lambda p, q: reads.evaluations(q),
        "getEvaluation": lambda p, q: reads.evaluation(p["evaluation_id"]),
        "getEvaluationPoints": lambda p, q: reads.evaluation_points(p["evaluation_id"], q),
    }
    handlers.update(extra_reads or {})
    commands = extra_commands or {}

    def endpoint(operation):
        async def handle(request: Request):
            authorize(request, operation)
            query, headers = parameters(request, operation)
            if "requestBody" in operation:
                from tram.infrastructure.contract import strict_json

                if (
                    request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    != "application/json"
                ):
                    raise ApplicationError("BAD_REQUEST", "Content-Type must be application/json")
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ApplicationError("BAD_REQUEST", "Request body exceeds 64 KiB")
                try:
                    command = strict_json(body)
                    schema = operation["requestBody"]["content"]["application/json"]["schema"]
                    contract.validator(schema).validate(command)
                except (ValueError, UnicodeDecodeError, RecursionError) as exc:
                    raise ApplicationError("BAD_REQUEST", "Invalid JSON body") from exc
                except ValidationError as exc:
                    raise ApplicationError(
                        "VALIDATION_ERROR",
                        "Body does not match the API contract",
                        ".".join(str(p) for p in exc.path) or "body",
                    ) from exc
                if operation["operationId"] in commands:
                    return await run_in_threadpool(
                        commands[operation["operationId"]], request.path_params, command
                    )
                run, created = await run_in_threadpool(
                    forecasts.create, command, "operator", headers["Idempotency-Key"]
                )
                return JSONResponse(
                    run,
                    status_code=202 if created else 200,
                    headers={"Location": f"/api/v1/forecast-runs/{run['id']}", "Retry-After": "2"},
                )
            result = await run_in_threadpool(
                handlers[operation["operationId"]], request.path_params, query
            )
            if operation["operationId"] == "getForecastRun" and result["status"] in (
                "queued",
                "running",
            ):
                return JSONResponse(result, headers={"Retry-After": "2"})
            return result

        return handle

    operations = {
        (method, path): op
        for path, methods in contract.document["paths"].items()
        for method, op in methods.items()
        if method in ("get", "post")
    }
    if {op["operationId"] for op in operations.values()} != set(handlers) | set(commands) | {
        "createForecastRun"
    }:
        raise ValueError("HTTP handlers and OpenAPI operations differ")
    for (method, path), operation in operations.items():
        app.add_api_route(
            "/api/v1" + path,
            endpoint(operation),
            methods=[method.upper()],
            operation_id=operation["operationId"],
            include_in_schema=False,
        )
    return app
