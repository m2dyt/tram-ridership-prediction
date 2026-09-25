"""Evaluate a trained model against the seasonal baseline on validation and test partitions.

Computes MAE and WAPE on identical points and generates a formal comparison report.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend" / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend" / "src"))
if str(ROOT / "ml" / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "ml" / "src"))

from tram.domain.metro import Quarter


def compute_metrics(actuals: list[float], preds: list[float]) -> dict[str, float | None]:
    if not actuals:
        return {"mae": 0.0, "wape": None, "count": 0}
    abs_errors = [abs(a - p) for a, p in zip(actuals, preds)]
    mae = sum(abs_errors) / len(actuals)
    actual_sum = sum(actuals)
    wape = (sum(abs_errors) / actual_sum) if actual_sum > 0 else None
    return {"mae": round(mae, 2), "wape": round(wape, 4) if wape is not None else None, "count": len(actuals)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate trained model against seasonal baseline")
    parser.add_argument("--model", type=Path, required=True, help="Path to saved model directory")
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("data/training/metro-v1"),
        help="Path to prepared features directory or features.jsonl",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("data/metro-evaluation/seasonal-20260922"),
        help="Path to baseline evaluation results directory (optional)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to write evaluation report JSON",
    )

    args = parser.parse_args(argv)
    model_dir: Path = args.model.resolve()

    if not model_dir.is_dir():
        print(f"Error: model directory not found: {model_dir}", file=sys.stderr)
        return 1

    import joblib
    import pandas as pd

    model = joblib.load(model_dir / "model.joblib")
    meta = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    feat_info = json.loads((model_dir / "features.json").read_text(encoding="utf-8"))

    splits = meta["splits"]
    train_start = Quarter.parse(splits["train_start"])
    val_start = Quarter.parse(splits["validation_start"])
    test_start = Quarter.parse(splits["test_start"])
    test_end = Quarter.parse(splits["test_end"])

    features_path: Path = args.features.resolve()
    features_file = features_path / "features.jsonl" if features_path.is_dir() else features_path
    rows = [
        json.loads(line)
        for line in features_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    feature_cols = feat_info["feature_columns"]
    cat_cols = feat_info["categorical_columns"]
    num_cols = [c for c in feature_cols if c not in cat_cols]

    def to_df(rows_data):
        records = []
        for r in rows_data:
            rec = {c: r.get(c) for c in num_cols}
            for c in cat_cols:
                rec[c] = str(r.get(c, "unknown"))
            records.append(rec)
        df = pd.DataFrame(records)
        for c in cat_cols:
            if hasattr(df[c], "astype"):
                df[c] = df[c].astype("category")
        return df

    # Baseline predictions index (if available)
    baseline_preds: dict[tuple[str, str], float | None] = {}
    baseline_dir = args.baseline.resolve() if args.baseline else None
    if baseline_dir and (baseline_dir / "predictions.jsonl").is_file():
        for line in (baseline_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                pred = item.get("prediction")
                baseline_preds[(item["series_id"], item["quarter"])] = (
                    float(pred) if pred is not None else None
                )

    report_partitions = {}

    for part_name, (start_q, end_q) in [
        ("validation", (val_start, test_start)),
        ("test", (test_start, test_end)),
    ]:
        part_rows = [
            r
            for r in rows
            if r["is_observed"]
            and r["target"] is not None
            and start_q <= Quarter.parse(r["quarter"]) < end_q
        ]

        if not part_rows:
            continue

        X_part = to_df(part_rows)
        actuals = [float(r["target"]) for r in part_rows]
        raw_preds = model.predict(X_part)
        clipped_preds = [max(0.0, float(p)) for p in raw_preds]

        cand_metrics = compute_metrics(actuals, clipped_preds)

        # Baseline comparison
        base_actuals = []
        base_preds = []
        matched_cand_preds = []
        for r, cp in zip(part_rows, clipped_preds):
            key = (r["series_id"], r["quarter"])
            if key in baseline_preds and baseline_preds[key] is not None:
                base_actuals.append(float(r["target"]))
                base_preds.append(baseline_preds[key])
                matched_cand_preds.append(cp)

        base_metrics = compute_metrics(base_actuals, base_preds) if base_actuals else None
        comp_metrics = (
            compute_metrics(base_actuals, matched_cand_preds) if base_actuals else None
        )

        wape_delta = None
        if (
            comp_metrics
            and comp_metrics.get("wape") is not None
            and base_metrics
            and base_metrics.get("wape") is not None
        ):
            wape_delta = round((comp_metrics["wape"] - base_metrics["wape"]) * 100, 2)

        report_partitions[part_name] = {
            "period": f"{start_q}..{end_q.shift(-1)}",
            "candidate_total": cand_metrics,
            "baseline_matched": base_metrics,
            "candidate_matched": comp_metrics,
            "wape_delta_pct_points": wape_delta,
        }

    report = {
        "model_version": model_dir.name,
        "model_type": meta.get("model_type"),
        "evaluated_at": datetime.now(UTC).isoformat(),
        "partitions": report_partitions,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report written to {args.output}")

    print("\n" + "=" * 60)
    print(f"EVALUATION RESULTS: {model_dir.name} ({meta.get('model_type')})")
    print("=" * 60)
    for part, data in report_partitions.items():
        print(f"\n--- Partition: {part.upper()} ({data['period']}) ---")
        cand = data["candidate_total"]
        print(f"Candidate MAE  : {cand['mae']} passengers / quarter (N={cand['count']})")
        print(f"Candidate WAPE : {round(cand['wape'] * 100, 2) if cand['wape'] else 'N/A'}%")
        if data.get("baseline_matched") and data.get("wape_delta_pct_points") is not None:
            base = data["baseline_matched"]
            delta = data["wape_delta_pct_points"]
            delta_str = f"{delta:+.2f}%"
            verdict = "IMPROVED" if delta < 0 else ("SAME" if delta == 0 else "DEGRADED")
            print(f"Baseline WAPE  : {round(base['wape'] * 100, 2)}% (N={base['count']})")
            print(f"WAPE Delta     : {delta_str} [{verdict}]")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
