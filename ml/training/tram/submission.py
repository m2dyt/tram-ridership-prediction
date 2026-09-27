"""Submission generation and formatting for Tram Ridership Prediction."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.validate_submission import validate_submission


def format_submission(
    grid_sub: pd.DataFrame,
    predictions: np.ndarray,
    sample_path: Path | None = None,
) -> pd.DataFrame:
    """Format predictions into competition submission DataFrame."""
    sub = grid_sub[["route", "date", "hour"]].copy()
    sub["prediction"] = np.clip(np.round(predictions), 0, None).astype(int)

    # Strict compliance: route 5 is forced to 0
    sub.loc[sub["route"] == 5, "prediction"] = 0

    # Align to canonical sample order if sample provided
    if sample_path and sample_path.is_file():
        sample_df = pd.read_csv(sample_path, sep=";")
        aligned = sample_df[["route", "date", "hour"]].merge(
            sub, on=["route", "date", "hour"], how="left"
        )
        aligned["prediction"] = aligned["prediction"].fillna(0).astype(int)
        return aligned

    return sub


def save_submission(
    submission_df: pd.DataFrame,
    output_path: Path,
    sample_path: Path | None = None,
    validate: bool = True,
) -> dict:
    """Save submission to CSV with ';' delimiter and run validation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    submission_df.to_csv(output_path, sep=";", index=False)

    val_result = {}
    if validate:
        val_result = validate_submission(output_path, sample_path=sample_path)
    return val_result


def generate_candidate_path(
    candidates_dir: Path,
    model_name: str,
) -> Path:
    """Generate timestamped candidate file path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return candidates_dir / f"submission_{model_name}_{timestamp}.csv"
