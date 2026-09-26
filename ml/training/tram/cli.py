from __future__ import annotations

import argparse
import sys
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

import pandas as pd

from ml.training.tram.features import build_feature_matrix
from ml.training.tram.baseline import (
    BASE_PROFILE_COL,
    calculate_historical_profiles,
    attach_historical_profiles,
)
from ml.training.tram.evaluation import (
    compute_wape_metrics,
    evaluate_by_route,
    format_evaluation_report,
)
from ml.training.tram.models import (
    train_validation_models,
    fit_final_and_predict,
)
from ml.training.tram.submission import (
    format_submission,
    save_submission,
    generate_candidate_path,
)


def train_and_evaluate(
    data_dir: Path,
    output_dir: Path,
    use_gpu: bool = True,
    model_type: str = "catboost",
    iterations: int = 2000,
    learning_rate: float = 0.04,
    depth: int = 6,
    use_residual: bool = True,
    per_route: bool = True,
    eval_only: bool = False,
    save_candidate: bool = True,
    use_weather: bool = True,
    weather_path: Path | None = None,
) -> dict:
    """Run full end-to-end training, validation, and optional submission generation."""
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir = output_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    grid_train, grid_val, grid_sub = build_feature_matrix(
        data_dir,
        use_weather=use_weather,
        weather_path=weather_path,
    )

    print(f"Train grid size: {len(grid_train):,} rows")
    print(f"Val grid size:   {len(grid_val):,} rows")
    print(f"Sub grid size:   {len(grid_sub):,} rows")

    # STAGE 1: LOCAL VALIDATION (Train: Jan-Aug, Valid: Sep-Oct)
    print("\n--- STAGE 1: LOCAL VALIDATION (Train: Jan-Aug, Valid: Sep-Oct) ---")
    profiles_train = calculate_historical_profiles(grid_train)
    train_feat = attach_historical_profiles(grid_train, profiles_train)
    val_feat = attach_historical_profiles(grid_val, profiles_train)

    val_models, val_preds, _ = train_validation_models(
        train_feat=train_feat,
        val_feat=val_feat,
        base_col=BASE_PROFILE_COL,
        model_type=model_type,
        iterations=iterations,
        learning_rate=learning_rate,
        depth=depth,
        use_gpu=use_gpu,
        use_residual=use_residual,
        per_route=per_route,
    )

    y_val = val_feat["boardings"].values
    val_metrics = compute_wape_metrics(y_val, val_preds)

    val_analysis = val_feat[["route", "boardings"]].copy()
    val_analysis["pred"] = val_preds
    per_route_metrics = evaluate_by_route(val_analysis)

    report_str = format_evaluation_report(val_metrics, per_route=per_route_metrics)
    print(report_str)

    if eval_only:
        print("\nEvaluation only mode requested: skipping Stage 2 final submission generation.")
        return {"val_metrics": val_metrics, "per_route": per_route_metrics}

    # STAGE 2: FULL RE-TRAINING (Jan-Oct 2025) FOR SUBMISSION
    print("\n--- STAGE 2: FULL RE-TRAINING (Jan-Oct 2025) FOR SUBMISSION ---")
    full_train = pd.concat([grid_train, grid_val], ignore_index=True)
    profiles_full = calculate_historical_profiles(full_train)

    full_train_feat = attach_historical_profiles(full_train, profiles_full)
    sub_feat = attach_historical_profiles(grid_sub, profiles_full)

    sub_preds = fit_final_and_predict(
        full_train_feat=full_train_feat,
        sub_feat=sub_feat,
        base_col=BASE_PROFILE_COL,
        val_models=val_models,
        model_type=model_type,
        iterations=iterations,
        learning_rate=learning_rate,
        depth=depth,
        use_gpu=use_gpu,
        use_residual=use_residual,
        per_route=per_route,
    )

    print("\nGenerating predictions for November - December 2025...")
    sample_file = data_dir / "test_submission.csv"
    submission_df = format_submission(
        grid_sub=grid_sub,
        predictions=sub_preds,
        sample_path=sample_file if sample_file.is_file() else None,
    )

    # Save to candidates first (Stage 0 compliance)
    if save_candidate:
        cand_path = generate_candidate_path(candidates_dir, model_type)
        save_submission(submission_df, cand_path, sample_path=sample_file, validate=True)
        print(f"\n[OK] Candidate submission saved to: {cand_path}")

    # Save to main submission file
    main_sub_file = output_dir / "submission.csv"
    val_result = save_submission(
        submission_df, main_sub_file, sample_path=sample_file, validate=True
    )
    print(f"[OK] Main submission file created at: {main_sub_file}")
    print(f"Total predicted passengers Nov-Dec: {submission_df['prediction'].sum():,}")
    if val_result.get("success"):
        print("[PASSED] Submission passed all official competition checks!")

    return {
        "val_metrics": val_metrics,
        "per_route": per_route_metrics,
        "submission_file": main_sub_file,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Train tram ridership prediction model with GPU support."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("dataset"),
        help="Path to directory containing dataset files (labels/, test_submission.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/predictions"),
        help="Directory to save submission.csv and candidate predictions",
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU execution (disable GPU)",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["catboost", "lightgbm", "histgradient", "baseline"],
        default="catboost",
        help="Model architecture: catboost (recommended for GPU), lightgbm, histgradient, or baseline",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=2000,
        help="Number of boosting iterations (default: 2000)",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.04,
        help="Learning rate (default: 0.04)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=6,
        help="Tree depth (default: 6)",
    )
    parser.add_argument(
        "--no-residual",
        action="store_true",
        help="Train directly on raw boardings rather than residual (delta) from base profile",
    )
    parser.add_argument(
        "--no-per-route",
        action="store_true",
        help="Train one single model for all routes instead of 9 dedicated per-route models",
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="Only run Stage 1 validation and print report without generating submission",
    )
    parser.add_argument(
        "--no-weather",
        action="store_true",
        help="Disable external Open-Meteo weather features",
    )
    parser.add_argument(
        "--weather-path",
        type=Path,
        default=None,
        help="Custom path to weather_hourly_2025.csv (defaults to data/weather_hourly_2025.csv)",
    )

    args = parser.parse_args()
    train_and_evaluate(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        use_gpu=not args.cpu,
        model_type=args.model,
        iterations=args.iterations,
        learning_rate=args.learning_rate,
        depth=args.depth,
        use_residual=not args.no_residual,
        per_route=not args.no_per_route,
        eval_only=args.eval_only,
        use_weather=not args.no_weather,
        weather_path=args.weather_path,
    )


if __name__ == "__main__":
    main()
