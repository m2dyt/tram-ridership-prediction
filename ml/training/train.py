"""Train regression or gradient boosting models on prepared quarterly features.

Adheres strictly to the evaluation protocol:
- Fits purely on the train partition (train_start <= quarter < validation_start).
- Validates hyperparameter performance on the validation partition.
- Exports a complete immutable model version with metadata, features, and model card.
"""

from __future__ import annotations

import argparse
import hashlib
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


def load_dataset(
    features_path: Path,
) -> tuple[list[dict], dict]:
    if features_path.is_dir():
        features_file = features_path / "features.jsonl"
        meta_file = features_path / "metadata.json"
    else:
        features_file = features_path
        meta_file = features_path.parent / "metadata.json"

    if not features_file.is_file():
        raise FileNotFoundError(f"Features file not found at {features_file}")

    rows = [
        json.loads(line)
        for line in features_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else {}
    return rows, meta


def compute_metrics(actuals: list[float], preds: list[float]) -> dict[str, float | None]:
    if not actuals:
        return {"mae": 0.0, "wape": None, "count": 0}
    abs_errors = [abs(a - p) for a, p in zip(actuals, preds)]
    mae = sum(abs_errors) / len(actuals)
    actual_sum = sum(actuals)
    wape = (sum(abs_errors) / actual_sum) if actual_sum > 0 else None
    return {"mae": round(mae, 2), "wape": round(wape, 4) if wape is not None else None, "count": len(actuals)}


def build_and_train_ridge(
    train_rows: list[dict],
    val_rows: list[dict],
    feature_cols: list[str],
    cat_cols: list[str],
    hyperparams: dict,
    seed: int = 42,
):
    import numpy as np
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    num_cols = [c for c in feature_cols if c not in cat_cols]

    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="unknown")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, num_cols),
            ("cat", categorical_transformer, cat_cols),
        ]
    )

    alpha = float(hyperparams.get("alpha", 1.0))
    model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("regressor", Ridge(alpha=alpha, random_state=seed)),
        ]
    )

    # Format training arrays
    def to_df(rows_data):
        import pandas as pd
        records = []
        for r in rows_data:
            rec = {c: r.get(c) for c in num_cols}
            for c in cat_cols:
                rec[c] = str(r.get(c, "unknown"))
            records.append(rec)
        return pd.DataFrame(records)

    X_train = to_df(train_rows)
    y_train = np.array([r["target"] for r in train_rows], dtype=float)

    model.fit(X_train, y_train)

    # Validation
    val_metrics = {}
    if val_rows:
        X_val = to_df(val_rows)
        y_val = [r["target"] for r in val_rows]
        raw_preds = model.predict(X_val)
        clipped_preds = [max(0.0, float(p)) for p in raw_preds]
        val_metrics = compute_metrics(y_val, clipped_preds)

    return model, val_metrics


def build_and_train_hist_gbdt(
    train_rows: list[dict],
    val_rows: list[dict],
    feature_cols: list[str],
    cat_cols: list[str],
    hyperparams: dict,
    seed: int = 42,
):
    import numpy as np
    import pandas as pd
    from sklearn.ensemble import HistGradientBoostingRegressor

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
            df[c] = df[c].astype("category")
        return df

    X_train = to_df(train_rows)
    y_train = np.array([r["target"] for r in train_rows], dtype=float)

    max_iter = int(hyperparams.get("max_iter", 100))
    learning_rate = float(hyperparams.get("learning_rate", 0.05))
    max_leaf_nodes = int(hyperparams.get("max_leaf_nodes", 31))

    model = HistGradientBoostingRegressor(
        max_iter=max_iter,
        learning_rate=learning_rate,
        max_leaf_nodes=max_leaf_nodes,
        categorical_features=cat_cols,
        random_state=seed,
    )

    model.fit(X_train, y_train)

    val_metrics = {}
    if val_rows:
        X_val = to_df(val_rows)
        y_val = [r["target"] for r in val_rows]
        raw_preds = model.predict(X_val)
        clipped_preds = [max(0.0, float(p)) for p in raw_preds]
        val_metrics = compute_metrics(y_val, clipped_preds)

    return model, val_metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train model on prepared features")
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("data/training/metro-v1"),
        help="Path to prepared features directory or features.jsonl",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to experiment JSON config",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to save output model version directory",
    )

    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    output_dir = args.output.resolve()

    if not config_path.is_file():
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        return 1

    config = json.loads(config_path.read_text(encoding="utf-8"))
    rows, feat_meta = load_dataset(args.features.resolve())

    train_start = Quarter.parse(config["train_start"])
    validation_start = Quarter.parse(config["validation_start"])
    test_start = Quarter.parse(config["test_start"])
    test_end = Quarter.parse(config["test_end"])

    feature_cols = config.get("feature_columns", feat_meta.get("feature_columns", []))
    cat_cols = config.get("categorical_columns", feat_meta.get("categorical_columns", []))
    model_type = config.get("model_type", "ridge").lower()
    hyperparams = config.get("hyperparameters", {})
    seed = int(config.get("seed", 42))

    # Split rows strictly by period
    train_rows = [
        r
        for r in rows
        if r["is_observed"]
        and r["target"] is not None
        and train_start <= Quarter.parse(r["quarter"]) < validation_start
    ]
    val_rows = [
        r
        for r in rows
        if r["is_observed"]
        and r["target"] is not None
        and validation_start <= Quarter.parse(r["quarter"]) < test_start
    ]

    print(
        f"Training set: {len(train_rows)} samples ({train_start}..{validation_start.shift(-1)}), "
        f"Validation set: {len(val_rows)} samples ({validation_start}..{test_start.shift(-1)})"
    )

    import joblib

    if model_type in ("ridge", "linear"):
        model, val_metrics = build_and_train_ridge(
            train_rows, val_rows, feature_cols, cat_cols, hyperparams, seed=seed
        )
    elif model_type in ("hist_gradient_boosting", "gbdt", "lightgbm"):
        model, val_metrics = build_and_train_hist_gbdt(
            train_rows, val_rows, feature_cols, cat_cols, hyperparams, seed=seed
        )
    else:
        print(f"Error: unknown model_type '{model_type}'", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    model_file = output_dir / "model.joblib"
    joblib.dump(model, model_file)

    meta = {
        "kind": "trained_model_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "model_type": model_type,
        "seed": seed,
        "splits": {
            "train_start": str(train_start),
            "validation_start": str(validation_start),
            "test_start": str(test_start),
            "test_end": str(test_end),
        },
        "sample_counts": {"train": len(train_rows), "validation": len(val_rows)},
        "hyperparameters": hyperparams,
        "validation_metrics": val_metrics,
        "features_info": {
            "feature_columns": feature_cols,
            "categorical_columns": cat_cols,
        },
    }

    (output_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "features.json").write_text(
        json.dumps({"feature_columns": feature_cols, "categorical_columns": cat_cols}, indent=2),
        encoding="utf-8",
    )

    # Model Card
    card_content = f"""# Model Card: {output_dir.name}

- **Model Type**: {model_type}
- **Trained At**: {meta['created_at']}
- **Training Period**: {train_start} to {validation_start.shift(-1)} ({len(train_rows)} samples)
- **Validation Period**: {validation_start} to {test_start.shift(-1)} ({len(val_rows)} samples)
- **Validation MAE**: {val_metrics.get('mae')} passengers / quarter
- **Validation WAPE**: {val_metrics.get('wape') * 100 if val_metrics.get('wape') is not None else 'N/A'}%

## Features
- Numerical: {', '.join(c for c in feature_cols if c not in cat_cols)}
- Categorical: {', '.join(cat_cols)}
"""
    (output_dir / "model-card.md").write_text(card_content, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "success",
                "model_dir": str(output_dir),
                "model_type": model_type,
                "validation_mae": val_metrics.get("mae"),
                "validation_wape": val_metrics.get("wape"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
