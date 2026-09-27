"""Full-path server benchmark: real HTTP API -> queue -> worker -> PostgreSQL.

Unlike scripts/benchmark_inference.py, which calls a Predictor directly
in-process and measures only its own memory/CPU, this script starts the
real server (`tram serve`, uvicorn) and the real worker (`tram worker`) as
separate OS processes against a real PostgreSQL database, then drives load
through actual HTTP requests — the same path a real client (or the React
frontend) experiences. It requires a reachable, migrated PostgreSQL
(TRAM_DATABASE_URL) and a published dataset revision with an "available"
forecast profile; see docs/OPERATIONS.md.

Measures, per full round trip (POST /forecast-runs -> poll until succeeded
-> GET .../points):
  - submit_latency_ms:   time for POST /forecast-runs to return
  - end_to_end_ms:       submit -> observed succeeded (includes the real
                          worker's poll interval, i.e. production behaviour,
                          not an artificially tightened loop)
  - read_points_ms:      time for GET .../points to return the result
  - RSS memory of the API and worker processes, sampled before/after load
  - throughput (round trips/sec across the whole batch), error rate

Usage:
  python scripts/benchmark_api.py --iterations 15
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def rss_mb(pid: int | None) -> float | None:
    if psutil is None or pid is None:
        return None
    try:
        return round(psutil.Process(pid).memory_info().rss / (1024 * 1024), 2)
    except psutil.Error:
        return None


def quantiles(values_ms: list[float]) -> dict:
    if not values_ms:
        return {
            "count": 0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
        }
    s = sorted(values_ms)
    n = len(s)

    def q(p):
        return s[min(n - 1, int(p * n))]

    return {
        "count": n,
        "min_ms": round(min(s), 3),
        "max_ms": round(max(s), 3),
        "mean_ms": round(statistics.mean(s), 3),
        "p50_ms": round(q(0.50), 3),
        "p95_ms": round(q(0.95), 3),
        "p99_ms": round(q(0.99), 3),
    }


def wait_for_health(client: httpx.Client, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/v1/health")
            if response.status_code == 200 and response.json().get("status") == "ready":
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"API did not become ready within {timeout_s}s: {last_error}")


def start_process(args: list[str], env: dict) -> subprocess.Popen:
    return subprocess.Popen(
        args,
        cwd=WORKSPACE_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def stop_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def run_benchmark(
    iterations: int,
    host: str,
    port: int,
    output_path: Path,
    poll_interval_s: float = 0.2,
    timeout_s: float = 30.0,
) -> dict:
    # Load .env the same way Settings() does (pydantic-settings reads it directly),
    # rather than depending on the calling shell having exported these vars —
    # each Bash tool call in this session starts a fresh shell with no persisted
    # environment, so relying on `source .env` from an earlier call is fragile.
    from dotenv import dotenv_values

    env = {
        k: v
        for k, v in {**dotenv_values(WORKSPACE_ROOT / ".env"), **os.environ}.items()
        if v is not None
    }
    operator_token = env.get("TRAM_OPERATOR_TOKEN")
    if not operator_token:
        raise RuntimeError(
            "TRAM_OPERATOR_TOKEN not found in .env or the environment; this "
            "benchmark uses the static operator token, not a JWT login, to stay "
            "independent of any seeded user (run `tram init-config` first)."
        )

    base_url = f"http://{host}:{port}"
    api_proc = start_process(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tram.composition:create_app",
            "--factory",
            "--host",
            host,
            "--port",
            str(port),
        ],
        env,
    )
    worker_proc = None
    try:
        with httpx.Client(base_url=base_url, timeout=timeout_s) as client:
            wait_for_health(client)
            # Worker is started only after the API is healthy: both connect to the
            # same PostgreSQL, and the API's own readiness proves migrations/DB
            # are reachable, so a slow-starting worker isn't confused for a DB
            # outage.
            worker_proc = start_process([sys.executable, "-m", "tram.cli", "worker"], env)
            time.sleep(1.0)  # let the worker's first claim loop start

            capabilities = (
                client.get(
                    "/api/v1/capabilities", headers={"Authorization": f"Bearer {operator_token}"}
                )
                .raise_for_status()
                .json()
            )
            profile = next(
                p for p in capabilities["forecast_profiles"] if p["availability"] == "available"
            )
            dataset_revision_id = capabilities["dataset_revision_id"]
            route_id = profile["route_ids"][0]
            as_of = profile["allowed_as_of_end"]
            forecast_start = profile["forecast_start_min"]

            headers = {"Authorization": f"Bearer {operator_token}"}
            submit_ms: list[float] = []
            end_to_end_ms: list[float] = []
            read_ms: list[float] = []
            errors = 0
            timed_out = 0

            start_rss_api = rss_mb(api_proc.pid)
            start_rss_worker = rss_mb(worker_proc.pid)
            batch_start = time.perf_counter()

            for _ in range(iterations):
                idem_key = f"bench-{uuid.uuid4()}"
                body = {
                    "dataset_revision_id": dataset_revision_id,
                    "profile_id": profile["id"],
                    "route_ids": [route_id],
                    "as_of": as_of,
                    "forecast_start": forecast_start,
                }
                t0 = time.perf_counter()
                try:
                    response = client.post(
                        "/api/v1/forecast-runs",
                        json=body,
                        headers={**headers, "Idempotency-Key": idem_key},
                    )
                    submit_ms.append((time.perf_counter() - t0) * 1000.0)
                    if response.status_code not in (200, 202):
                        errors += 1
                        continue
                    run_id = response.json()["id"]
                except httpx.HTTPError:
                    submit_ms.append((time.perf_counter() - t0) * 1000.0)
                    errors += 1
                    continue

                deadline = time.monotonic() + timeout_s
                status = None
                while time.monotonic() < deadline:
                    poll = client.get(f"/api/v1/forecast-runs/{run_id}", headers=headers)
                    status = poll.json()["status"]
                    if status in ("succeeded", "failed"):
                        break
                    time.sleep(poll_interval_s)
                end_to_end_ms.append((time.perf_counter() - t0) * 1000.0)
                if status != "succeeded":
                    errors += 1
                    if status not in ("failed",):
                        timed_out += 1
                    continue

                t1 = time.perf_counter()
                points = client.get(
                    f"/api/v1/forecast-runs/{run_id}/points",
                    params={"from": forecast_start, "to": poll.json()["forecast_end"]},
                    headers=headers,
                )
                read_ms.append((time.perf_counter() - t1) * 1000.0)
                if points.status_code != 200:
                    errors += 1

            wall_s = time.perf_counter() - batch_start
            end_rss_api = rss_mb(api_proc.pid)
            end_rss_worker = rss_mb(worker_proc.pid)

        result = {
            "timestamp": datetime.now(UTC).isoformat(),
            "target": base_url,
            "dataset_revision_id": dataset_revision_id,
            "profile_id": profile["id"],
            "model_method_expected": "seasonal_naive_v1 or an active bundle, see forecast-run.model.method in raw responses",
            "iterations": iterations,
            "errors": errors,
            "timed_out": timed_out,
            "error_rate_pct": round((errors / iterations) * 100.0, 2) if iterations else 0.0,
            "wall_clock_s": round(wall_s, 3),
            "round_trips_per_sec": round(iterations / wall_s, 3) if wall_s > 0 else 0.0,
            "submit_latency_ms": quantiles(submit_ms),
            "end_to_end_ms": quantiles(end_to_end_ms),
            "read_points_ms": quantiles(read_ms),
            "memory": {
                "api_start_rss_mb": start_rss_api,
                "api_end_rss_mb": end_rss_api,
                "worker_start_rss_mb": start_rss_worker,
                "worker_end_rss_mb": end_rss_worker,
            },
        }
    finally:
        stop_process(worker_proc)
        stop_process(api_proc)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
    existing["server_scenario"] = result
    output_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", "-n", type=int, default=15)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--output", "-o", type=Path, default=Path("benchmarks/latest.json"))
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Per-request/poll timeout in seconds"
    )
    args = parser.parse_args()

    result = run_benchmark(
        iterations=args.iterations,
        host=args.host,
        port=args.port,
        output_path=args.output,
        timeout_s=args.timeout,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
