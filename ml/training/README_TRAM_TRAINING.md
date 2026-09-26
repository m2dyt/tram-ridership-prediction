# Tram competition trainer: command and limitations

[`train_tram.py`](train_tram.py) is an offline experiment which prepares route × date × hour forecasts and writes `submission.csv`. It is not wired to the FastAPI prediction worker. The code expects challenge files under `dataset/` (by default), including `labels/` and `test_submission.csv`; `dataset/` is ignored by Git, so a new clone will not necessarily have them.

## Before using it

Read the [global project plan](../../00_ГЛОБАЛЬНЫЙ_ПЛАН_К_ЭТАЛОНУ.md). Verify the archive and data dictionary first. In particular, the current code fills missing joined target rows with zero, uses manual route/seasonal adjustments, forces route 5 to zero in the submission, and assumes exactly 14,640 test rows. Each choice requires validation against the actual challenge schema and fixed temporal validation. The organizer Q&A says route 5 must be present and may be zero; this does not validate any other rows.

Older descriptions of a “90.3%+” score or expected improvement are not verified in this repository. Cite a score only with its exact data/checksum, split, code/config, predictions and platform receipt. Do not use final test labels for model selection.

## Current command interface

From the repository root with Python dependencies installed:

```powershell
python ml/training/train_tram.py --help
```

Arguments include `--data-dir`, `--output-dir`, `--cpu`, `--model`, `--iterations`, `--learning-rate`, `--depth`, `--no-residual` and `--no-per-route`. The implementation currently offers `catboost`, `lightgbm`, `histgradient` and `baseline`; the default data path and optional model dependencies must be checked before launch. `--help` is safe and does not train. Run training only after input and validation review; retain the existing best submission separately.

The script writes a semicolon-delimited CSV with `route;date;hour;prediction` and currently checks a fixed expected row count. The caller must independently verify unique keys, exact match to the supplied sample, finite nonnegative predictions and route-5 presence. Its printout alone is not a scored submission.

## Inputs and dependencies

The original challenge archive is linked from the user-provided specification: [dataset.zip](https://disk.yandex.ru/d/DiFwlfMOauxjBg). Save the original and data dictionary in `sources/`, record provenance and SHA-256, and put derived files under `data/`. The script imports the ML stack lazily, but the repo has a legacy `requirements-gpu.txt` in addition to root `requirements.txt`; dependency consolidation is an explicit item in the global plan.
