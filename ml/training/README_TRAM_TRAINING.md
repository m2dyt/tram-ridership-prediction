# Tram competition trainer: modular architecture and usage

The tram training pipeline is modularized under [`ml/training/tram/`](tram/):
* [`features.py`](tram/features.py): Cartesian grid generation (`date x hour x route`), Russian official calendar 2025, cyclical and peak hour encodings.
* [`baseline.py`](tram/baseline.py): Leak-free historical passenger profiles, non-summer profiles, weekend repair tracking, blended baseline predictor.
* [`evaluation.py`](tram/evaluation.py): WAPE, competition WAPE-score, MAE, per-route slicing.
* [`models.py`](tram/models.py): Residual learning target formulation, CatBoost (GPU/CPU), LightGBM, HistGradientBoosting, and Baseline.
* [`submission.py`](tram/submission.py): Route 5 zero forcing, sample alignment, candidate saving in `ml/predictions/candidates/`.
* [`cli.py`](tram/cli.py): CLI interface.
* [`train_tram.py`](train_tram.py): Backwards-compatible facade.

---

## Command Interface

From the repository root:

```powershell
# Show help
python ml/training/train_tram.py --help

# Fast evaluation-only run on baseline profile (Sep-Oct 2025 validation):
python ml/training/train_tram.py --model baseline --eval-only

# Train per-route CatBoost models with GPU:
python ml/training/train_tram.py --model catboost

# Train fast HistGradientBoosting models on CPU:
python ml/training/train_tram.py --model histgradient --cpu
```

### Outputs
- Submissions are saved to `ml/predictions/submission.csv` and automatically duplicated with a timestamp to `ml/predictions/candidates/`.
- Every generated submission is automatically checked by `scripts/validate_submission.py`.
