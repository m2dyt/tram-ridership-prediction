"""Unit tests for the inference latency and throughput benchmark script."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.benchmark_inference import (
    calculate_quantiles,
    make_synthetic_history,
    run_benchmark,
)


class TestBenchmark(unittest.TestCase):
    def test_calculate_quantiles(self):
        latencies = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = calculate_quantiles(latencies)

        self.assertEqual(stats["count"], 5)
        self.assertEqual(stats["min_ms"], 10.0)
        self.assertEqual(stats["max_ms"], 50.0)
        self.assertEqual(stats["mean_ms"], 30.0)
        self.assertEqual(stats["p50_ms"], 30.0)
        self.assertAlmostEqual(stats["rps"], 1000.0 / 30.0, places=1)

    def test_calculate_quantiles_empty(self):
        stats = calculate_quantiles([])
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["rps"], 0.0)

    def test_make_synthetic_history(self):
        routes = ["1", "17"]
        history = make_synthetic_history(routes)
        # 2 routes * 168 hours = 336 observations
        self.assertEqual(len(history), 336)
        self.assertEqual(history[0].spatial.route_id, "1")

    def test_run_benchmark_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_json = Path(tmp_dir) / "test_benchmark.json"
            results = run_benchmark(
                models_root=Path("models/tram"),
                iterations=1,
                output_path=out_json,
                quiet=True,
            )
            self.assertIsNotNone(results)

            self.assertTrue(out_json.exists(), "Benchmark JSON report was not written")
            with out_json.open("r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertIn("timestamp", data)
            self.assertIn("environment", data)
            self.assertIn("scenarios", data)
            self.assertIn("24h_SingleRoute", data["scenarios"])
            if "ArtifactPredictor" in data["scenarios"]["24h_SingleRoute"]:
                ap_metrics = data["scenarios"]["24h_SingleRoute"]["ArtifactPredictor"]["metrics"]
                self.assertGreater(ap_metrics["mean_ms"], 0.0)
                self.assertEqual(
                    data["scenarios"]["24h_SingleRoute"]["ArtifactPredictor"]["errors"], 0
                )
            else:
                self.assertIn("SeasonalNaive", data["scenarios"]["24h_SingleRoute"])
                sn_metrics = data["scenarios"]["24h_SingleRoute"]["SeasonalNaive"]["metrics"]
                self.assertGreater(sn_metrics["mean_ms"], 0.0)
                self.assertEqual(data["scenarios"]["24h_SingleRoute"]["SeasonalNaive"]["errors"], 0)


if __name__ == "__main__":
    unittest.main()
