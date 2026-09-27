"""End-to-end check of a running stack: auth, model registry and model serving.

Starts real `uvicorn` (tram.composition:create_app) and `tram worker` against
TRAM_DATABASE_URL, then over HTTP:

1. /health reports database and model readiness;
2. an operator account is created with the static operator token, then
   login -> /auth/me -> /auth/refresh -> /auth/logout -> refresh after logout
   (must be 401);
3. /models and /models/{active} are read;
4. every available forecast profile of --dataset gets one run; each run must
   succeed, and with --expect-bundle VERSION the hourly runs must be pinned to
   that bundle while the others use seasonal_naive_v1. For bundle runs the
   returned values are compared with a direct call to the same bundle.

Requires a migrated database, a published dataset (see docs/OPERATIONS.md)
and, for --expect-bundle, the bundle under TRAM_MODELS_ROOT (models/tram).
Exit code 0 only if every check passed; a JSON report is printed.

Usage:
  python scripts/smoke_model_serving.py --dataset <revision> [--expect-bundle <version>]
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


class Checks:
    def __init__(self):
        self.results = []

    def check(self, name, ok, detail=None):
        self.results.append({"check": name, "ok": bool(ok), "detail": detail})
        return ok

    @property
    def passed(self):
        return all(r["ok"] for r in self.results)


def environment():
    from dotenv import dotenv_values

    merged = {**dotenv_values(WORKSPACE_ROOT / ".env"), **os.environ}
    return {k: v for k, v in merged.items() if v is not None}


def start(args, env):
    return subprocess.Popen(
        args,
        cwd=WORKSPACE_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def stop(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def wait_ready(client, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/v1/health")
            if response.status_code in (200, 503):
                return response
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("API did not answer /health in time")


def refresh_cookie(response):
    # The cookie is Secure; over plain HTTP the client would not resend it by itself.
    return response.cookies.get("tram_refresh")


def auth_flow(client, static_operator, checks):
    username, password = f"smoke-{uuid.uuid4().hex[:12]}", uuid.uuid4().hex
    created = client.post(
        "/api/v1/auth/operators",
        json={"username": username, "password": password},
        headers={"Authorization": f"Bearer {static_operator}"},
    )
    checks.check(
        "create operator with static token", created.status_code == 200, created.status_code
    )
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    if not checks.check("login", login.status_code == 200, login.status_code):
        return None
    body = login.json()
    token, cookie = body["access_token"], refresh_cookie(login)
    checks.check("login returns operator role", body.get("role") == "operator", body.get("role"))
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    checks.check(
        "me", me.status_code == 200 and me.json().get("username") == username, me.status_code
    )
    refreshed = client.post("/api/v1/auth/refresh", headers={"Cookie": f"tram_refresh={cookie}"})
    ok = refreshed.status_code == 200
    data = refreshed.json() if ok else {}
    checks.check(
        "refresh returns role and user",
        ok and data.get("role") == "operator" and data.get("user", {}).get("username") == username,
        {"status": refreshed.status_code, "keys": sorted(data)},
    )
    new_cookie = refresh_cookie(refreshed) or cookie
    checks.check("refresh rotates the session cookie", new_cookie != cookie)
    reused = client.post("/api/v1/auth/refresh", headers={"Cookie": f"tram_refresh={cookie}"})
    checks.check(
        "rotated-out refresh token is rejected", reused.status_code == 401, reused.status_code
    )
    logout = client.post(
        "/api/v1/auth/logout", json={}, headers={"Cookie": f"tram_refresh={new_cookie}"}
    )
    checks.check("logout", logout.status_code == 204, logout.status_code)
    after = client.post("/api/v1/auth/refresh", headers={"Cookie": f"tram_refresh={new_cookie}"})
    checks.check("refresh after logout is rejected", after.status_code == 401, after.status_code)
    return data.get("access_token") or token


def bundle_values(version, run, route_id):
    """Values the bundle itself produces for the run's window (independent of the API)."""
    from tram.domain.series import SpatialKey, SpatialLevel
    from tram.domain.time import Horizon, Interval, Resolution, parse_time
    from tram.infrastructure.ml.artifact_predictor import ArtifactPredictor

    models_root = Path(os.environ.get("TRAM_MODELS_ROOT", WORKSPACE_ROOT / "models" / "tram"))
    predictor = ArtifactPredictor.from_version(models_root, version)
    window = Interval(parse_time(run["forecast_start"]), parse_time(run["forecast_end"]))
    predictions = predictor.predict(
        (),
        (SpatialKey(level=SpatialLevel.ROUTE, route_id=route_id),),
        window,
        Horizon(run["profile"]["horizon"]),
        Resolution(run["profile"]["resolution"]),
        parse_time(run["as_of"]),
    )
    return {p.interval.start.isoformat(): p.value for p in predictions}


def forecast_runs(client, token, dataset, expect_bundle, checks, timeout):
    headers = {"Authorization": f"Bearer {token}"}
    caps = client.get(
        "/api/v1/capabilities", params={"dataset_revision_id": dataset}, headers=headers
    )
    if not checks.check("capabilities", caps.status_code == 200, caps.status_code):
        return []
    report = []
    for profile in caps.json()["forecast_profiles"]:
        if profile["availability"] != "available":
            continue
        body = {
            "dataset_revision_id": dataset,
            "profile_id": profile["id"],
            "route_ids": profile["route_ids"][:1],
            "as_of": profile["allowed_as_of_end"],
            "forecast_start": profile["forecast_start_min"],
        }
        created = client.post(
            "/api/v1/forecast-runs",
            json=body,
            headers={**headers, "Idempotency-Key": f"smoke-{uuid.uuid4()}"},
        )
        status = created.status_code
        if not checks.check(
            f"{profile['id']}: create run", status == 202, status if status == 202 else created.text
        ):
            continue
        run = created.json()
        deadline = time.monotonic() + timeout
        while run["status"] in ("queued", "running") and time.monotonic() < deadline:
            time.sleep(0.5)
            run = client.get(f"/api/v1/forecast-runs/{run['id']}", headers=headers).json()
        model = run["model"]
        entry = {
            "profile": profile["id"],
            "resolution": profile["resolution"],
            "status": run["status"],
            "model": {"method": model["method"], "version": model["version"]},
            "warnings": run["warnings"],
            "failure": run["failure"],
        }
        report.append(entry)
        checks.check(f"{profile['id']}: succeeded", run["status"] == "succeeded", run["failure"])
        if expect_bundle:
            wants_bundle = profile["resolution"] == "hour"
            expected = (
                ("tram_bundle", expect_bundle) if wants_bundle else ("seasonal_naive_v1", None)
            )
            got = (model["method"], model["version"] if wants_bundle else None)
            checks.check(f"{profile['id']}: pinned model", got == expected, entry["model"])
        if run["status"] != "succeeded":
            continue
        points = client.get(
            f"/api/v1/forecast-runs/{run['id']}/points",
            params={"from": run["forecast_start"], "to": run["forecast_end"], "limit": 1000},
            headers=headers,
        ).json()["items"]
        entry["points"] = len(points)
        entry["first_values"] = [p["value"] for p in points[:6]]
        if model["method"] == "tram_bundle":
            direct = bundle_values(model["version"], run, body["route_ids"][0])
            served = {p["interval_start"]: p["value"] for p in points}
            checks.check(
                f"{profile['id']}: served values equal a direct bundle call",
                served == direct and len(served) > 0,
                {"served": len(served), "direct": len(direct)},
            )
    return report


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--dataset", required=True, help="Published dataset_revision_id to forecast"
    )
    parser.add_argument("--expect-bundle", default=None, help="Bundle version hourly runs must use")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8095)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    env = environment()
    static_operator = env.get("TRAM_OPERATOR_TOKEN")
    if not static_operator:
        sys.exit("TRAM_OPERATOR_TOKEN is not set in .env or the environment")
    checks, report = Checks(), {}
    api = start(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tram.composition:create_app",
            "--factory",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        env,
    )
    worker = None
    try:
        with httpx.Client(base_url=f"http://{args.host}:{args.port}", timeout=30) as client:
            health = wait_ready(client).json()
            report["health"] = health
            checks.check("health ready", health.get("status") == "ready", health)
            if args.expect_bundle:
                checks.check(
                    "health serves the expected bundle",
                    health.get("model") == "ok"
                    and health.get("model_version") == args.expect_bundle,
                    {k: health.get(k) for k in ("model", "model_version")},
                )
            worker = start([sys.executable, "-m", "tram.cli", "worker"], env)
            time.sleep(1.0)
            checks.check("worker started", worker.poll() is None, worker.poll())
            token = auth_flow(client, static_operator, checks)
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            models = client.get("/api/v1/models", headers=headers)
            listing = models.json() if models.status_code == 200 else {}
            active = [m for m in listing.get("items", []) if m.get("is_active")]
            report["models"] = [
                {k: m.get(k) for k in ("id", "method", "status", "is_active")}
                for m in listing.get("items", [])
            ]
            checks.check("list models", models.status_code == 200, models.status_code)
            if active:
                detail = client.get(f"/api/v1/models/{active[0]['id']}", headers=headers)
                checks.check("read active model", detail.status_code == 200, detail.status_code)
            if token:
                report["runs"] = forecast_runs(
                    client, token, args.dataset, args.expect_bundle, checks, args.timeout
                )
    finally:
        stop(worker)
        stop(api)
    report["checks"] = checks.results
    report["passed"] = checks.passed
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if checks.passed else 1


if __name__ == "__main__":
    sys.exit(main())
