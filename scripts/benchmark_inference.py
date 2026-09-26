"""Inference Latency and Throughput Benchmark.

Measures:
  - Latency quantiles: min, max, mean, p50, p90, p95, p99 (milliseconds)
  - Throughput: RPS (requests per second), points/sec
  - Memory: Peak heap memory (tracemalloc) and RSS (psutil if available)
  - Error rate

Outputs:
  - Formatted ASCII table in stdout
  - Machine-readable JSON report saved to benchmarks/latest.json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import statistics
import sys
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure workspace root and backend/src and ml/src are on sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
backend_src = WORKSPACE_ROOT / "backend" / "src"
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))
ml_src = WORKSPACE_ROOT / "ml" / "src"
if str(ml_src) not in sys.path:
    sys.path.insert(0, str(ml_src))

from tram.domain.series import Observation, SpatialKey, SpatialLevel  # noqa: E402
from tram.domain.time import MOSCOW, Horizon, Interval, Resolution, aware  # noqa: E402
from tram.infrastructure.ml.artifact_predictor import ArtifactPredictor  # noqa: E402
from tram_ml.baseline import SeasonalNaive  # noqa: E402


def get_rss_memory_mb() -> float | None:
    """Return process RSS memory in MB if psutil is available."""
    try:
        import psutil

        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / (1024 * 1024), 2)
    except Exception:
        return None


def calculate_quantiles(latencies_ms: list[float]) -> dict[str, float]:
    """Calculate statistical quantiles and throughput from a list of latencies in ms."""
    if not latencies_ms:
        return {
            "count": 0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p90_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "rps": 0.0,
        }

    sorted_lat = sorted(latencies_ms)
    n = len(sorted_lat)

    def quantile(p: float) -> float:
        index = int(p * n)
        if index >= n:
            index = n - 1
        return sorted_lat[index]

    mean_ms = statistics.mean(latencies_ms)
    rps = round(1000.0 / mean_ms, 2) if mean_ms > 0 else 0.0

    return {
        "count": n,
        "min_ms": round(min(latencies_ms), 3),
        "max_ms": round(max(latencies_ms), 3),
        "mean_ms": round(mean_ms, 3),
        "p50_ms": round(quantile(0.50), 3),
        "p90_ms": round(quantile(0.90), 3),
        "p95_ms": round(quantile(0.95), 3),
        "p99_ms": round(quantile(0.99), 3),
        "rps": rps,
    }


def benchmark_predictor_scenario(
    predictor,
    route_ids: list[str],
    hours: int,
    iterations: int,
    history: tuple = (),
    warmup: int = 2,
) -> dict:
    series = tuple(
        SpatialKey(level=SpatialLevel.ROUTE, route_id=r) for r in route_ids
    )
    # Start at Moscow midnight
    start = aware(datetime(2025, 11, 1, 0, 0, tzinfo=MOSCOW))
    end = start + timedelta(hours=hours)
    window = Interval(start, end)
    as_of = start

    is_seasonal_naive = isinstance(predictor, SeasonalNaive)

    def do_predict():
        if is_seasonal_naive and hours > 24:
            all_preds = []
            days = hours // 24
            for d in range(days):
                day_start = start + timedelta(days=d)
                day_end = day_start + timedelta(days=1)
                day_preds = predictor.predict(
                    history=history,
                    series=series,
                    window=Interval(day_start, day_end),
                    horizon=Horizon.DAY,
                    resolution=Resolution.HOUR,
                    as_of=as_of,
                )
                all_preds.extend(day_preds)
            return all_preds
        else:
            return predictor.predict(
                history=history,
                series=series,
                window=window,
                horizon=Horizon.DAY,
                resolution=Resolution.HOUR,
                as_of=as_of,
            )

    # Warmup runs
    for _ in range(warmup):
        with contextlib.suppress(Exception):
            do_predict()

    latencies_ms: list[float] = []
    errors = 0
    total_points = 0

    tracemalloc.start()
    start_rss = get_rss_memory_mb()

    for _ in range(iterations):
        t0 = time.perf_counter()
        try:
            preds = do_predict()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(elapsed_ms)
            total_points = len(preds)
        except Exception:
            errors += 1
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    end_rss = get_rss_memory_mb()

    stats = calculate_quantiles(latencies_ms)
    points_per_sec = (
        round(total_points * (1000.0 / stats["mean_ms"]), 1)
        if stats["mean_ms"] > 0
        else 0.0
    )

    return {
        "routes": route_ids,
        "hours": hours,
        "total_points_per_request": total_points,
        "iterations": iterations,
        "errors": errors,
        "error_rate_pct": round((errors / iterations) * 100.0, 2),
        "metrics": stats,
        "points_per_sec": points_per_sec,
        "memory": {
            "tracemalloc_peak_mb": round(peak_mem / (1024 * 1024), 3),
            "start_rss_mb": start_rss,
            "end_rss_mb": end_rss,
        },
    }


def make_synthetic_history(route_ids: list[str]) -> tuple:
    """Generate 7 days of hourly historical observations prior to 2025-11-01 for testing."""
    start = aware(datetime(2025, 11, 1, 0, 0, tzinfo=MOSCOW))
    obs = []
    for r in route_ids:
        sp = SpatialKey(level=SpatialLevel.ROUTE, route_id=r)
        for h in range(168):  # 7 days * 24 hours
            ref_start = start - timedelta(hours=168 - h)
            ref_end = ref_start + timedelta(hours=1)
            inter = Interval(ref_start, ref_end)
            val = 50 + (h % 24) * 10
            obs.append(Observation(spatial=sp, interval=inter, available_at=ref_end, value=val))
    return tuple(obs)


def run_benchmark(
    models_root: Path,
    version: str | None = None,
    iterations: int = 10,
    output_path: Path | None = None,
    quiet: bool = False,
) -> dict:
    """Execute full benchmark suite comparing ArtifactPredictor and SeasonalNaive."""
    # 1. Initialize predictors
    fallback = SeasonalNaive()
    artifact_predictor = None
    try:
        artifact_predictor = ArtifactPredictor.from_active_version(
            models_root=models_root,
            fallback=fallback,
            specific_version=version,
        )
    except Exception as exc:
        if not quiet:
            print(f"[BENCHMARK] Warning: could not load ArtifactPredictor: {exc}")

    predictors_to_test = []
    if artifact_predictor:
        predictors_to_test.append(("ArtifactPredictor", artifact_predictor))
    predictors_to_test.append(("SeasonalNaive", fallback))

    # 2. Define scenarios
    scenarios = [
        {"name": "24h_SingleRoute", "routes": ["17"], "hours": 24},
        {"name": "24h_MultiRoute", "routes": ["1", "17", "25", "38"], "hours": 24},
        {"name": "168h_Week_MultiRoute", "routes": ["1", "17", "25", "38"], "hours": 168},
        {"name": "60d_Full_AllRoutes", "routes": ["1", "5", "7", "11", "12", "17", "25", "26", "28", "38"], "hours": 1464},
    ]

    results: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": {
            "python_version": sys.version.split()[0],
            "os": platform.system(),
            "os_release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "model_version": (
            artifact_predictor.bundle.version
            if artifact_predictor and artifact_predictor.bundle
            else "None"
        ),
        "iterations": iterations,
        "scenarios": {},
    }

    if not quiet:
        print("=" * 82)
        print(" TRAM RIDERSHIP INFERENCE LATENCY & THROUGHPUT BENCHMARK")
        print("=" * 82)
        print(f" Environment : {platform.system()} {platform.release()} ({platform.machine()})")
        print(f" Python      : {sys.version.split()[0]}")
        print(f" Model Bundle: {results['model_version']}")
        print(f" Iterations  : {iterations} per scenario")
        print("-" * 82)
        header = f"{'Predictor':<18} | {'Scenario':<20} | {'p50(ms)':<8} | {'p95(ms)':<8} | {'p99(ms)':<8} | {'RPS':<7} | {'Pts/sec':<9}"
        print(header)
        print("-" * 82)

    for scen in scenarios:
        scen_name = scen["name"]
        results["scenarios"][scen_name] = {}
        synth_history = make_synthetic_history(scen["routes"])

        for pred_name, predictor in predictors_to_test:
            bench_res = benchmark_predictor_scenario(
                predictor=predictor,
                route_ids=scen["routes"],
                hours=scen["hours"],
                iterations=iterations,
                history=synth_history,
            )
            results["scenarios"][scen_name][pred_name] = bench_res

            if not quiet:
                m = bench_res["metrics"]
                p50 = f"{m['p50_ms']:.2f}"
                p95 = f"{m['p95_ms']:.2f}"
                p99 = f"{m['p99_ms']:.2f}"
                rps = f"{m['rps']:.1f}"
                pts = f"{bench_res['points_per_sec']:.0f}"
                print(f"{pred_name:<18} | {scen_name:<20} | {p50:<8} | {p95:<8} | {p99:<8} | {rps:<7} | {pts:<9}")

    if not quiet:
        print("=" * 82)

    # 3. Save JSON report
    if output_path is None:
        output_path = WORKSPACE_ROOT / "benchmarks" / "latest.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    if not quiet:
        print(f"[BENCHMARK] Saved detailed benchmark report to: {output_path}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Tram Predictor Latency & Throughput Benchmark")
    parser.add_argument("--iterations", "-n", type=int, default=10, help="Number of benchmark iterations")
    parser.add_argument("--version", type=str, default=None, help="Model version to test (defaults to active version)")
    parser.add_argument("--models-root", type=Path, default=Path("models/tram"), help="Root models directory")
    parser.add_argument("--output", "-o", type=Path, default=Path("benchmarks/latest.json"), help="Output JSON path")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode (no console table)")
    args = parser.parse_args()

    run_benchmark(
        models_root=args.models_root,
        version=args.version,
        iterations=args.iterations,
        output_path=args.output,
        quiet=args.quiet,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
