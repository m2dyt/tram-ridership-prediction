"""Train the service model and export it as model bundles.

    python -m ml.training.tram.service --data-dir dataset --version service-2025-11-01 --set-active

Two bundles are written:

* ``<version>`` is the served model, refitted on all history (training_history_end is the
  day after the last label). Its metrics come from the holdout check below.
* ``<version>-check`` is the same recipe fitted only on history before the holdout weeks.
  ``tram evaluate --model-version <version>-check`` replays it on the holdout honestly,
  because none of those weeks were seen in training.

Weather is not used: on 2025 data even the observed weather did not lower the error,
and at serving time only a forecast of the weather would be known.
"""

from __future__ import annotations

import argparse
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from ml.training.tram.adaptive import (
    CATEGORICAL,
    DEFAULT_PARAMS,
    FEATURES,
    HOLDOUT_WEEKS,
    RECENT_DAYS,
    RECIPE,
    train_service_model,
)
from ml.training.tram.bundle import export_model_bundle, set_active_version
from ml.training.tram.features import ALL_ROUTES

MOSCOW = ZoneInfo("Europe/Moscow")
LABEL_FILES = ("labels_day_train.csv", "labels_day_test.csv")


def read_labels(data_dir: Path) -> pd.DataFrame:
    frames = []
    for name in LABEL_FILES:
        path = data_dir / "labels" / name
        if path.is_file():
            frames.append(pd.read_csv(path, sep=";"))
    if not frames:
        raise FileNotFoundError(f"No label files in {data_dir / 'labels'}")
    labels = pd.concat(frames, ignore_index=True)
    return labels[["route", "date", "hour", "boardings"]]


def _midnight(day: pd.Timestamp) -> str:
    return datetime.combine(day.date(), time.min, MOSCOW).isoformat()


def export_service_bundles(
    labels: pd.DataFrame,
    version: str,
    models_root: Path,
    holdout_weeks: int = HOLDOUT_WEEKS,
    overwrite: bool = False,
    set_active: bool = False,
) -> dict:
    result = train_service_model(labels, holdout_weeks=holdout_weeks)
    features_spec = {
        "feature_cols": FEATURES,
        "categorical_features": CATEGORICAL,
        "base_profile_col": "base",
        "route_categorical_features": [],
    }
    common = {
        "model_type": "histgradient",
        "recipe": RECIPE,
        "params": DEFAULT_PARAMS,
        "recent_days": RECENT_DAYS,
        "use_residual": True,
        "per_route": False,
        "use_weather": False,
        "spatial_levels": ["route", "stop"],
        # Routes without any labels (5 is closed) are served too: no boardings means zero.
        "routes": sorted(set(result.routes) | set(ALL_ROUTES)),
        "training_history_start": _midnight(result.history_start),
        "holdout_start": _midnight(result.holdout_start),
    }
    bundles = {
        version: (result.final_model, result.history_end),
        f"{version}-check": (result.check_model, result.holdout_start),
    }
    for name, (model, history_end) in bundles.items():
        estimator = {
            "recipe": RECIPE,
            "model": model if result.use_model else None,
            "use_model": result.use_model,
            "recent_days": RECENT_DAYS,
            "intervals": result.intervals,
        }
        export_model_bundle(
            version=name,
            models=estimator,
            profiles={},
            metrics=result.metrics,
            config={**common, "training_history_end": _midnight(history_end)},
            models_root=models_root,
            overwrite=overwrite,
            features_spec=features_spec,
        )
    if set_active:
        set_active_version(version, models_root=models_root)
    return result.metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train and export the service model")
    parser.add_argument("--data-dir", type=Path, default=Path("dataset"))
    parser.add_argument("--models-root", type=Path, default=Path("models/tram"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--holdout-weeks", type=int, default=HOLDOUT_WEEKS)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--set-active", action="store_true")
    args = parser.parse_args(argv)
    metrics = export_service_bundles(
        read_labels(args.data_dir),
        args.version,
        args.models_root,
        holdout_weeks=args.holdout_weeks,
        overwrite=args.overwrite,
        set_active=args.set_active,
    )
    holdout = metrics["holdout"]
    print(
        f"Holdout {holdout['start']} – {holdout['end']}: base WAPE {holdout['base_wape']:.4f}, "
        f"base + model WAPE {holdout['model_wape']:.4f}; serving the {metrics['selected']}"
    )
    print(f"Interval coverage on the check weeks: {metrics['intervals']['check_coverage']:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
