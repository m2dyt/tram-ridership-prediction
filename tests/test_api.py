import json
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient
from tram.api.app import create_http_app
from tram.api.extensions import context_bindings, occupancy_bindings
from tram.application.context import ContextService
from tram.application.occupancy import OccupancyService
from tram.application.service import ForecastService, ReadService
from tram.application.worker import RunWorker
from tram.infrastructure.context_store import SqlSnapshotStore
from tram.infrastructure.contract import Contract
from tram.infrastructure.database import Base, make_engine, session_factory
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SignedCursor
from tram.infrastructure.sources import ExternalSources
from tram.infrastructure.trips import SqlTripStore
from tram_ml.baseline import SeasonalNaive

from ml.training.tram.bundle import export_model_bundle, set_active_version
from tests.support import ROOT, FrozenClock, seed_trusted_fixture


@pytest.fixture
def models_root(tmp_path):
    return tmp_path / "models"


@pytest.fixture
def model_bundle(models_root):
    return export_model_bundle(
        "baseline_v1",
        models=None,
        profiles={},
        metrics={"wape": 0.1, "wape_score": 0.9, "mae": 2.0},
        config={"model_type": "baseline", "use_residual": False},
        models_root=models_root,
    )


@pytest.fixture
def api(tmp_path):
    models_root = tmp_path / "models"
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    seed_trusted_fixture(sessions)
    repo, clock, contract = SqlRepository(sessions), FrozenClock(), Contract(ROOT / "openapi.yaml")
    reads = ReadService(repo, clock, SignedCursor("c" * 32))
    extra_reads, extra_commands = occupancy_bindings(
        OccupancyService(SqlTripStore(sessions), clock, reads)
    )
    context_reads, context_commands = context_bindings(
        ContextService(SqlSnapshotStore(sessions), ExternalSources(), clock, reads)
    )
    from tram.api.extensions import auth_bindings
    from tram.api.models import get_model, list_models
    from tram.application.auth import AuthService
    from tram.infrastructure.auth import (
        Argon2PasswordHasher,
        JwtTokenIssuer,
        SqlSessionStore,
        SqlUserRepository,
    )

    auth_service = AuthService(
        users=SqlUserRepository(sessions),
        sessions=SqlSessionStore(sessions),
        hasher=Argon2PasswordHasher(),
        issuer=JwtTokenIssuer("secret"),
        clock=clock,
        access_ttl=900,
        refresh_ttl=86400,
    )
    auth_reads, auth_commands = auth_bindings(auth_service)
    extra_reads.update(context_reads)
    extra_reads.update(auth_reads)
    extra_reads["listModels"] = lambda p, q: list_models(models_root)
    extra_reads["getModel"] = lambda p, q: get_model(models_root, p["model_id"])
    extra_commands.update(context_commands)
    extra_commands.update(auth_commands)
    app = create_http_app(
        reads,
        ForecastService(repo, clock, reads),
        contract,
        viewer_token="v" * 32,
        operator_token="o" * 32,
        unavailable_errors=(ConnectionError,),
        extra_reads=extra_reads,
        extra_commands=extra_commands,
        auth_service=auth_service,
    )
    with TestClient(app) as client:
        yield client, contract, RunWorker(repo, clock, SeasonalNaive())
    engine.dispose()


def checked(api, method, path, status=200, role="viewer", **kwargs):
    client, contract, _ = api
    headers = kwargs.pop("headers", {})
    if role:
        headers["Authorization"] = "Bearer " + ("v" if role == "viewer" else "o") * 32
    response = client.request(method, "/api/v1" + path, headers=headers, **kwargs)
    assert response.status_code == status, response.text
    assert response.headers["X-Request-ID"]
    operation_path = (
        next(p for p in contract.document["paths"] if p == path)
        if path in contract.document["paths"]
        else None
    )
    if operation_path is None:
        for candidate in contract.document["paths"]:
            left, right = candidate.split("/"), path.split("/")
            if len(left) == len(right) and all(
                a == b or a.startswith("{") for a, b in zip(left, right, strict=True)
            ):
                operation_path = candidate
                break
    spec = contract.document["paths"][operation_path][method.lower()]
    declared = contract.resolve(spec["responses"][str(status)])
    content = declared["content"][response.headers["content-type"].split(";")[0]]
    contract.validator(content["schema"]).validate(response.json())
    return response


def test_catalog_auth_errors_and_swagger(api):
    checked(api, "GET", "/health", role=None)
    checked(api, "GET", "/capabilities", role=None, status=401)
    checked(api, "GET", "/capabilities")
    checked(api, "GET", "/data-status")
    checked(
        api,
        "GET",
        "/network",
        params={"network_revision_id": "demo-network-v1", "valid_at": "2026-09-21"},
    )
    query = {"network_revision_id": "demo-network-v1", "valid_at": "2026-09-21"}
    checked(api, "GET", "/routes", params=query)
    checked(api, "GET", "/routes/demo-route-01", params=query)
    checked(api, "GET", "/stops", params=query)
    checked(api, "GET", "/routes", params={**query, "unexpected": 1}, status=422)
    checked(
        api, "GET", "/routes", params=list(query.items()) + [("limit", 1), ("limit", 2)], status=422
    )
    checked(api, "GET", "/routes", params={**query, "limit": "1.2"}, status=422)
    checked(api, "GET", "/evaluations")
    checked(api, "GET", "/evaluations/00000000-0000-4000-8000-000000000001", status=404)
    assert api[0].get("/docs").status_code == 200
    assert api[0].get("/openapi.json").json() == api[1].document


def test_model_registry_reads_valid_bundle_and_reports_missing_version(
    api, models_root, model_bundle
):
    set_active_version("baseline_v1", models_root=models_root)
    items = checked(api, "GET", "/models").json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "available"
    assert items[0]["is_active"] is True
    assert items[0]["method"] == "baseline"
    assert items[0]["metrics"]["wape"] == 0.1

    detail = checked(api, "GET", "/models/baseline_v1").json()
    assert detail["config"]["model_type"] == "baseline"
    assert "Model Card" in detail["card"]
    assert checked(api, "GET", "/models/absent", status=404).json()["code"] == "NOT_FOUND"


def test_model_registry_marks_incomplete_bundle_and_preserves_valid_one(
    api, models_root, model_bundle
):
    (models_root / "unfinished_v1").mkdir()
    items = checked(api, "GET", "/models").json()["items"]
    assert [(item["id"], item["status"]) for item in items] == [
        ("baseline_v1", "available"),
        ("unfinished_v1", "invalid"),
    ]
    assert "manifest.json" in items[1]["error"]
    response = checked(api, "GET", "/models/unfinished_v1", status=503)
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert str(models_root) not in response.text


@pytest.mark.parametrize(
    "filename", ["manifest.json", "config.json", "metrics.json", "features.json"]
)
def test_model_registry_rejects_broken_json(api, model_bundle, filename):
    (model_bundle / filename).write_text("{broken", encoding="utf-8")
    item = checked(api, "GET", "/models").json()["items"][0]
    assert item["status"] == "invalid"
    assert filename in item["error"]
    checked(api, "GET", "/models/baseline_v1", status=503)


@pytest.mark.parametrize("field,value", [("version", "other_v1"), ("format_version", "2.0")])
def test_model_registry_rejects_mismatched_version_and_format(api, model_bundle, field, value):
    manifest_path = model_bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    item = checked(api, "GET", "/models").json()["items"][0]
    assert item["status"] == "invalid"
    checked(api, "GET", "/models/baseline_v1", status=503)


def test_model_registry_rejects_checksum_mismatch(api, model_bundle):
    (model_bundle / "metrics.json").write_text('{"wape": 0.2}', encoding="utf-8")
    item = checked(api, "GET", "/models").json()["items"][0]
    assert item["status"] == "invalid"
    assert "metrics.json" in item["error"]


@pytest.mark.parametrize(
    "field,value", [("estimator_size_bytes", 1), ("artifacts", []), ("created_at", None)]
)
def test_model_registry_rejects_incomplete_manifest(api, model_bundle, field, value):
    manifest_path = model_bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    item = checked(api, "GET", "/models").json()["items"][0]
    assert item["status"] == "invalid"


@pytest.mark.parametrize(
    "filename", ["estimator.joblib", "config.json", "metrics.json", "model-card.md"]
)
def test_model_registry_rejects_missing_bundle_file(api, model_bundle, filename):
    (model_bundle / filename).unlink()
    item = checked(api, "GET", "/models").json()["items"][0]
    assert item["status"] == "invalid"
    assert filename in item["error"]


@pytest.mark.parametrize(
    "filename,content",
    [
        ("config.json", "[]"),
        ("config.json", '{"model_type": "baseline", "model_type": "other"}'),
        ("features.json", '{"feature_cols": "route"}'),
        (
            "features.json",
            '{"feature_cols": ["route"], "categorical_features": [], "base_profile_col": "baseline"}',
        ),
        ("metrics.json", '{"wape": NaN}'),
    ],
)
def test_model_registry_rejects_invalid_json_structure(api, model_bundle, filename, content):
    artifact_path = model_bundle / filename
    artifact_path.write_text(content, encoding="utf-8")
    manifest_path = model_bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        if artifact["file"] == filename:
            artifact["sha256"] = sha256(artifact_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    item = checked(api, "GET", "/models").json()["items"][0]
    assert item["status"] == "invalid"
    assert filename in item["error"]


def test_model_registry_rejects_unsafe_directory(api, models_root, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    models_root.mkdir()
    (models_root / "linked_v1").symlink_to(outside, target_is_directory=True)
    item = checked(api, "GET", "/models").json()["items"][0]
    assert item["id"] == "linked_v1"
    assert item["status"] == "invalid"
    checked(api, "GET", "/models/linked_v1", status=503)


def test_model_registry_reports_invalid_directory_name_consistently(api, models_root):
    models_root.mkdir()
    (models_root / "bad version").mkdir()
    item = checked(api, "GET", "/models").json()["items"][0]
    assert item["id"] == "bad version"
    assert item["status"] == "invalid"
    checked(api, "GET", "/models/bad%20version", status=503)


def test_model_registry_reports_directory_named_like_active_pointer(api, models_root):
    models_root.mkdir()
    (models_root / "active_version.txt").mkdir()
    response = checked(api, "GET", "/models")
    assert [(item["id"], item["status"]) for item in response.json()["items"]] == [
        ("active_version.txt", "invalid")
    ]
    checked(api, "GET", "/models/active_version.txt", status=503)


def test_model_registry_marks_missing_active_bundle(api, models_root):
    set_active_version("missing_v1", models_root=models_root)
    item = checked(api, "GET", "/models").json()["items"][0]
    assert item["id"] == "missing_v1"
    assert item["is_active"] is True
    assert item["status"] == "invalid"
    assert "missing" in item["error"]


@pytest.mark.parametrize(
    "pointer_kind,error",
    [
        ("symlink", "unsafe active_version.txt"),
        ("empty", "invalid active_version.txt"),
        ("bad_utf8", "invalid active_version.txt"),
    ],
)
def test_model_registry_keeps_healthy_bundle_visible_with_bad_active_pointer(
    api, models_root, model_bundle, tmp_path, pointer_kind, error
):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    pointer = models_root / "active_version.txt"
    if pointer_kind == "symlink":
        pointer.symlink_to(outside)
    elif pointer_kind == "empty":
        pointer.write_text("", encoding="utf-8")
    else:
        pointer.write_bytes(b"\xff")
    response = checked(api, "GET", "/models")
    assert [(item["id"], item["status"]) for item in response.json()["items"]] == [
        ("baseline_v1", "available")
    ]
    assert response.json()["active_version_error"] == error
    detail = checked(api, "GET", "/models/baseline_v1").json()
    assert detail["status"] == "available"
    assert detail["active_version_error"] == error
    assert "secret" not in response.text


@pytest.mark.parametrize(
    "horizon,start", [("day", "2026-09-21"), ("month", "2026-09-21"), ("year", "2026-10-01")]
)
def test_full_forecast_pipeline_and_contract(api, horizon, start):
    caps = checked(api, "GET", "/capabilities").json()
    profile = next(p for p in caps["forecast_profiles"] if p["horizon"] == horizon)
    command = {
        "dataset_revision_id": caps["dataset_revision_id"],
        "profile_id": profile["id"],
        "route_ids": profile["route_ids"],
        "as_of": "2026-09-20T18:00:00+03:00",
        "forecast_start": start + "T00:00:00+03:00",
    }
    headers = {"Idempotency-Key": "api-test-" + horizon}
    checked(api, "POST", "/forecast-runs", json=command, headers=headers.copy(), status=403)
    run = checked(
        api,
        "POST",
        "/forecast-runs",
        json=command,
        headers=headers.copy(),
        role="operator",
        status=202,
    ).json()
    path = "/forecast-runs/" + run["id"]
    checked(api, "GET", path)
    query = {"from": run["forecast_start"], "to": run["forecast_end"]}
    checked(api, "GET", path + "/points", params=query, status=409)
    assert api[2].execute_one()
    completed = checked(api, "GET", path).json()
    assert completed["status"] == "succeeded"
    points = checked(api, "GET", path + "/points", params={**query, "limit": 1}).json()
    map_result = checked(
        api, "GET", path + "/map", params={"interval_start": points["items"][0]["interval_start"]}
    ).json()
    assert points["items"][0] == map_result["features"][0]["properties"]
    assert points["page"]["has_more"]
    next_page = checked(
        api,
        "GET",
        path + "/points",
        params={**query, "limit": 1, "cursor": points["page"]["next_cursor"]},
    ).json()
    assert next_page["items"][0]["interval_start"] != points["items"][0]["interval_start"]
    checked(api, "GET", path + "/points", params={**query, "cursor": "tampered"}, status=400)
    checked(api, "POST", "/forecast-runs", json=command, headers=headers.copy(), role="operator")
    checked(
        api,
        "POST",
        "/forecast-runs",
        json={**command, "route_ids": ["missing"]},
        headers=headers.copy(),
        role="operator",
        status=409,
    )
    checked(api, "GET", "/forecast-runs", params={"status": "succeeded"})


@pytest.mark.parametrize(
    "body,status", [('{"profile_id": 1, "profile_id": 2}', 400), ('{"x": NaN}', 400), ("{}", 422)]
)
def test_invalid_command_json(api, body, status):
    checked(
        api,
        "POST",
        "/forecast-runs",
        role="operator",
        status=status,
        content=body,
        headers={"Content-Type": "application/json", "Idempotency-Key": "json-test-key"},
    )


def test_unavailable_evaluation_is_readable_without_fabricated_scores(api):
    from tram.infrastructure.database import EvaluationRow

    repository = api[2].repository
    dataset = repository.dataset("demo-data-v1")
    profile = dataset["capabilities"]["forecast_profiles"][0]
    model = dataset["models"][0]["model"]
    evaluation_id = "00000000-0000-4000-8000-000000000002"
    summary = {
        "id": evaluation_id,
        "dataset_revision_id": "demo-data-v1",
        "network_revision_id": "demo-network-v1",
        "source_mode": "demo",
        "profile": profile,
        "model": model,
        "status": "unavailable",
        "created_at": api[2].clock.now().isoformat(),
        "limitations": ["No evaluation has been performed"],
    }
    report = {
        "summary": summary,
        "folds": [],
        "scores": [],
        "peak_rule": "Not evaluated",
        "baseline_definitions": {"seasonal_naive": "Previous available week", "regression": None},
        "feature_availability_policy": "Only data available at as_of",
        "warnings": ["Synthetic test report"],
    }
    with repository.sessions.begin() as session:
        session.add(
            EvaluationRow(
                id=evaluation_id,
                dataset_id="demo-data-v1",
                profile_id=profile["id"],
                horizon=profile["horizon"],
                model_id=model["id"],
                status="unavailable",
                created_at=api[2].clock.now(),
                document=report,
            )
        )
    assert checked(api, "GET", "/evaluations").json()["items"] == [summary]
    assert checked(api, "GET", "/evaluations/" + evaluation_id).json() == report
    query = {"from": "2026-09-19T00:00:00+03:00", "to": "2026-09-20T00:00:00+03:00"}
    assert (
        checked(api, "GET", f"/evaluations/{evaluation_id}/points", params=query).json()["items"]
        == []
    )
    checked(
        api,
        "GET",
        f"/evaluations/{evaluation_id}/points",
        params={**query, "fold_id": "missing"},
        status=404,
    )


@pytest.mark.parametrize("error_type,status", [(RuntimeError, 500), (ConnectionError, 503)])
def test_internal_errors_do_not_expose_secrets(api, monkeypatch, error_type, status):
    def broken(_):
        raise error_type("sensitive-database-connection-string")

    monkeypatch.setattr(api[2].repository, "dataset", broken)
    response = checked(api, "GET", "/capabilities", status=status)
    assert "sensitive" not in response.text


def test_health_reports_database_failure(api, monkeypatch):
    monkeypatch.setattr(api[2].repository, "healthy", lambda: False)
    response = checked(api, "GET", "/health", role=None, status=503)
    assert response.json()["database"] == "down"


@pytest.mark.parametrize("invalid_time", ["2026-09-19T08:00:00", "2026-09-19T08:00:00+03:99"])
def test_observations_reject_invalid_timestamps(api, invalid_time):
    query = {
        "dataset_revision_id": "demo-data-v1",
        "observation_profile_id": "demo-validations-stop-hour",
        "from": "2026-09-19T08:00:00+03:00",
        "to": "2026-09-19T09:00:00+03:00",
    }
    checked(api, "GET", "/observations", params=query)
    checked(api, "GET", "/observations", params={**query, "from": invalid_time}, status=422)


def test_jwt_authorization_flow(api):
    client, _, _ = api

    # 1. We can use the static token first
    response = client.get("/api/v1/capabilities", headers={"Authorization": "Bearer " + "v" * 32})
    assert response.status_code == 200

    # 2. Login with seeded testuser
    response = client.post(
        "/api/v1/auth/login", json={"username": "testuser", "password": "password"}
    )
    assert response.status_code == 200, response.json()
    data = response.json()
    access_token = data["access_token"]
    assert "tram_refresh" in response.cookies
    refresh_token = response.cookies["tram_refresh"]

    # 3. Use the JWT access token to get capabilities
    response = client.get(
        "/api/v1/capabilities", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200

    # 4. Get user info
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"

    # 6. Refresh the token
    response = client.post("/api/v1/auth/refresh", cookies={"tram_refresh": refresh_token})
    assert response.status_code == 200

    # 7. Logout
    new_refresh = response.cookies.get("tram_refresh", refresh_token)
    response = client.post(
        "/api/v1/auth/logout", cookies={"tram_refresh": new_refresh}, json={"everywhere": False}
    )
    assert response.status_code == 204
