# ml/training — offline model experiments

This directory contains two separate forecasting paths. The tram competition script targets route-by-date-by-hour passenger flow. The other prepare/train/evaluate scripts work with quarterly Moscow metro data. Neither result should be described as the other task's model.

## Files

| File | Responsibility |
|---|---|
| [`train_tram.py`](train_tram.py) | Tram competition feature preparation, temporal validation, candidate/baseline calculations and submission CSV generation. Audit the input archive, missing-vs-zero semantics and claims in the companion document before treating the output as validated. |
| [`README_TRAM_TRAINING.md`](README_TRAM_TRAINING.md) | Existing tram command notes. Historical accuracy statements there are unverified; use current data and validation reports before citing a score. |
| [`prepare.py`](prepare.py) | Convert a metro prepared bundle to a quarterly training feature dataset. |
| [`train.py`](train.py) | Fit configured quarterly metro candidates and write an artifact/metadata. |
| [`evaluate.py`](evaluate.py) | Evaluate a saved metro candidate against a baseline. |
| [`requirements-gpu.txt`](requirements-gpu.txt) | Legacy standalone CatBoost/LightGBM dependency list; currently duplicates the root dependency mechanism and needs consolidation under the one-requirements policy. |
| [`__init__.py`](__init__.py) | Package marker. |

## Use this directory carefully

1. Start from the [project's global plan](../../00_ГЛОБАЛЬНЫЙ_ПЛАН_К_ЭТАЛОНУ.md).
2. Keep original datasets and source metadata in `sources/`; put normalized/versioned data and split reports under `data/`. Both data areas may be ignored by Git.
3. Do not tune on the final test period. Save each experiment's input hashes, config, split boundaries, predictions, metrics and candidate ID.
4. Keep model training outside FastAPI/worker startup and HTTP requests. Backend integration goes through the `Predictor` port after model artifact review.

The example command lines in older documents may depend on local datasets or directories that are not part of the repository. Check each command's current `--help` and actual input bundle before running it. The project test setup and Python environment are documented in [`docs/LOCAL_SETUP.md`](../../docs/LOCAL_SETUP.md).
