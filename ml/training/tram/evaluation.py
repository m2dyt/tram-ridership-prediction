"""Evaluation metrics and error analysis for Tram Ridership Prediction."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_wape_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute WAPE, competition WAPE-score, and MAE.
    
    WAPE = sum(|y - y_pred|) / sum(y)
    WAPE-score = max(0.0, 1.0 - WAPE)
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    abs_errors = np.abs(y_true - y_pred)
    sum_y = float(np.sum(y_true))
    sum_abs_err = float(np.sum(abs_errors))

    wape = (sum_abs_err / sum_y) if sum_y > 0 else 0.0
    wape_score = max(0.0, 1.0 - wape)
    mae = float(np.mean(abs_errors)) if len(abs_errors) > 0 else 0.0

    return {
        "wape": float(wape),
        "wape_score": float(wape_score),
        "mae": float(mae),
        "sum_y": sum_y,
        "sum_abs_err": sum_abs_err,
        "count": len(y_true),
    }


def evaluate_by_route(df_with_preds: pd.DataFrame) -> dict[int, dict[str, float]]:
    """Compute WAPE metrics per route."""
    results = {}
    for r in sorted(df_with_preds["route"].unique()):
        sub_r = df_with_preds[df_with_preds["route"] == r]
        y_true = sub_r["boardings"].values
        y_pred = sub_r["pred"].values
        results[int(r)] = compute_wape_metrics(y_true, y_pred)
    return results


def format_evaluation_report(
    overall_metrics: dict[str, float],
    per_route: dict[int, dict[str, float]] | None = None,
    title: str = "VALIDATION RESULTS (Sep-Oct 2025)",
) -> str:
    """Format human-readable evaluation report."""
    lines = [
        "",
        "=" * 67,
        f"{title:^67}",
        "=" * 67,
        f"Overall MAE:        {overall_metrics['mae']:.2f}",
        f"Overall WAPE:       {overall_metrics['wape']:.4f} ({overall_metrics['wape'] * 100:.2f}%)",
        f"Overall WAPE-score: {overall_metrics['wape_score']:.4f}",
        "Baseline was ~0.48. Higher is better!",
        "=" * 67,
    ]

    if per_route:
        lines.append("\nPer-Route WAPE Performance:")
        for r, m in per_route.items():
            lines.append(
                f"  Route {r:2d}: sum_y={int(m['sum_y']):8d}, WAPE={m['wape']:.4f}, WAPE-score={m['wape_score']:.4f}"
            )

    return "\n".join(lines)
