"""Model bundle serialization, verification, and loading for Tram Ridership Prediction.

Guarantees:
1. Immutable, versioned bundles in models/tram/<version>/.
2. Checksum validation (SHA-256) on load to prevent tampering.
3. Clean inference interface (TramModelBundle.predict).
4. Model card, feature schema, and experiment metadata tracking.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ml.training.tram.baseline import BASE_PROFILE_COL, attach_historical_profiles
from ml.training.tram.features import (
    ACTIVE_ROUTES,
    CATEGORICAL_FEATURES,
    FEATURE_COLS,
    ROUTE_CAT_FEATURES,
)


class BundleError(Exception):
    pass


class ChecksumMismatchError(BundleError):
    pass


class BundleNotFoundError(BundleError):
    pass


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_git_commit() -> str | None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return None


@dataclass
class TramModelBundle:
    version: str
    models: dict[int, Any] | Any
    profiles: dict[str, pd.DataFrame]
    feature_cols: list[str]
    categorical_features: list[str]
    base_col: str = BASE_PROFILE_COL
    use_residual: bool = True
    per_route: bool = True
    config: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Run batch inference on a feature matrix or Cartesian grid."""
        df_feat = df.copy()

        # 1. Add calendar features if missing
        if "dow_effective" not in df_feat.columns:
            from ml.training.tram.features import add_calendar_features

            df_feat = add_calendar_features(df_feat)

        # 2. Attach historical profiles if not already attached
        if self.base_col not in df_feat.columns:
            df_feat = attach_historical_profiles(df_feat, self.profiles)

        base_vals = df_feat[self.base_col].values
        active_features = [c for c in self.feature_cols if c in df_feat.columns]
        active_route_features = [c for c in active_features if c != "route"]

        preds = np.zeros(len(df_feat), dtype=float)

        if self.models is None or self.config.get("model_type") == "baseline":
            # Pure baseline prediction
            preds = base_vals.copy()
        elif self.per_route:
            for r in ACTIVE_ROUTES:
                mask_r = df_feat["route"] == r
                if not mask_r.any():
                    continue
                if r in self.models:
                    m_r = self.models[r]
                    X_r = df_feat.loc[mask_r, active_route_features]
                    raw_preds = m_r.predict(X_r)
                    preds[mask_r] = (
                        (base_vals[mask_r] + raw_preds) if self.use_residual else raw_preds
                    )
                else:
                    preds[mask_r] = base_vals[mask_r]
        else:
            X = df_feat[active_features]
            raw_preds = self.models.predict(X)
            preds = (base_vals + raw_preds) if self.use_residual else raw_preds

        # Postprocessing: non-negative integer and zero-force route 5
        preds = np.clip(np.round(preds), 0, None)
        if "route" in df_feat.columns:
            preds[df_feat["route"].values == 5] = 0

        return preds


def export_model_bundle(
    version: str,
    models: dict[int, Any] | Any,
    profiles: dict[str, pd.DataFrame],
    metrics: dict[str, Any],
    config: dict[str, Any],
    models_root: Path = Path("models/tram"),
    overwrite: bool = False,
) -> Path:
    """Export an immutable versioned model bundle with manifest and checksums."""
    bundle_dir = models_root / version
    if bundle_dir.exists() and not overwrite:
        raise BundleError(
            f"Model bundle version '{version}' already exists at {bundle_dir}. "
            "Use overwrite=True to replace."
        )

    bundle_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save estimator bundle (models + profiles)
    estimator_data = {
        "models": models,
        "profiles": profiles,
        "version": version,
    }
    estimator_file = bundle_dir / "estimator.joblib"
    joblib.dump(estimator_data, estimator_file, compress=3)
    estimator_hash = sha256_file(estimator_file)

    # 2. Features specification
    features_spec = {
        "feature_cols": FEATURE_COLS,
        "categorical_features": CATEGORICAL_FEATURES,
        "base_profile_col": BASE_PROFILE_COL,
        "route_categorical_features": ROUTE_CAT_FEATURES,
    }
    (bundle_dir / "features.json").write_text(
        json.dumps(features_spec, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 3. Config
    (bundle_dir / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 4. Metrics
    (bundle_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 5. Manifest
    manifest = {
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": get_git_commit(),
        "estimator_file": "estimator.joblib",
        "estimator_sha256": estimator_hash,
        "estimator_size_bytes": estimator_file.stat().st_size,
        "format_version": "1.0",
        "artifacts": [
            {"file": "estimator.joblib", "sha256": estimator_hash},
            {"file": "features.json", "sha256": sha256_file(bundle_dir / "features.json")},
            {"file": "config.json", "sha256": sha256_file(bundle_dir / "config.json")},
            {"file": "metrics.json", "sha256": sha256_file(bundle_dir / "metrics.json")},
        ],
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 6. Model Card
    card_content = f"""# Model Card: Tram Ridership Predictor `{version}`

## Overview
* **Version:** `{version}`
* **Created:** {manifest["created_at"]}
* **Git Commit:** `{manifest["git_commit"] or "N/A"}`
* **Model Type:** `{config.get("model_type", "unknown")}`
* **Residual Learning:** `{config.get("use_residual", True)}`
* **Per Route Models:** `{config.get("per_route", True)}`

## Performance (Sep-Oct 2025 Validation)
* **Overall WAPE:** `{metrics.get("wape", 0.0):.4f}` ({metrics.get("wape", 0.0) * 100:.2f}%)
* **Overall WAPE-score:** `{metrics.get("wape_score", 0.0):.4f}`
* **Overall MAE:** `{metrics.get("mae", 0.0):.2f}`

## Artifacts
* `estimator.joblib` (SHA-256: `{estimator_hash}`)
"""
    (bundle_dir / "model-card.md").write_text(card_content, encoding="utf-8")

    print(f"Exported model bundle to: {bundle_dir}")
    print(f"  Estimator SHA-256: {estimator_hash}")
    return bundle_dir


def load_model_bundle(
    version_or_path: str | Path,
    models_root: Path = Path("models/tram"),
    verify_checksum: bool = True,
) -> TramModelBundle:
    """Load a versioned model bundle with checksum verification."""
    path = Path(version_or_path)
    if not path.is_dir():
        bundle_dir = models_root / str(version_or_path)
    else:
        bundle_dir = path

    if not bundle_dir.is_dir():
        raise BundleNotFoundError(f"Bundle directory not found: {bundle_dir}")

    manifest_file = bundle_dir / "manifest.json"
    estimator_file = bundle_dir / "estimator.joblib"
    features_file = bundle_dir / "features.json"
    config_file = bundle_dir / "config.json"
    metrics_file = bundle_dir / "metrics.json"

    if not manifest_file.is_file():
        raise BundleError(f"Missing manifest.json in {bundle_dir}")
    if not estimator_file.is_file():
        raise BundleError(f"Missing estimator.joblib in {bundle_dir}")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    # Security: Checksum verification
    if verify_checksum:
        expected_hash = manifest.get("estimator_sha256")
        actual_hash = sha256_file(estimator_file)
        if expected_hash and actual_hash != expected_hash:
            raise ChecksumMismatchError(
                f"Checksum mismatch for {estimator_file}!\n"
                f"  Expected: {expected_hash}\n"
                f"  Actual:   {actual_hash}"
            )

    # Load artifacts
    estimator_data = joblib.load(estimator_file)
    features_spec = (
        json.loads(features_file.read_text(encoding="utf-8")) if features_file.is_file() else {}
    )
    config = json.loads(config_file.read_text(encoding="utf-8")) if config_file.is_file() else {}
    metrics = json.loads(metrics_file.read_text(encoding="utf-8")) if metrics_file.is_file() else {}

    return TramModelBundle(
        version=manifest.get("version", bundle_dir.name),
        models=estimator_data.get("models"),
        profiles=estimator_data.get("profiles"),
        feature_cols=features_spec.get("feature_cols", FEATURE_COLS),
        categorical_features=features_spec.get("categorical_features", CATEGORICAL_FEATURES),
        base_col=features_spec.get("base_profile_col", BASE_PROFILE_COL),
        use_residual=config.get("use_residual", True),
        per_route=config.get("per_route", True),
        config=config,
        metrics=metrics,
    )


def set_active_version(version: str, models_root: Path = Path("models/tram")) -> None:
    """Set active model version pointer."""
    models_root.mkdir(parents=True, exist_ok=True)
    ptr_file = models_root / "active_version.txt"
    ptr_file.write_text(version.strip(), encoding="utf-8")
    print(f"Active model version set to: '{version}' ({ptr_file})")


def get_active_version(models_root: Path = Path("models/tram")) -> str | None:
    """Read current active model version pointer."""
    ptr_file = models_root / "active_version.txt"
    if ptr_file.is_file():
        return ptr_file.read_text(encoding="utf-8").strip()
    return None
