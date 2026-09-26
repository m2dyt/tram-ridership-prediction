"""Tram ridership prediction training and feature engineering package."""

from ml.training.tram.baseline import (
    BASE_PROFILE_COL,
    attach_historical_profiles,
    calculate_historical_profiles,
    predict_seasonal_baseline,
)
from ml.training.tram.evaluation import (
    compute_wape_metrics,
    evaluate_by_route,
    format_evaluation_report,
)
from ml.training.tram.features import (
    ACTIVE_ROUTES,
    ALL_ROUTES,
    CATEGORICAL_FEATURES,
    FEATURE_COLS,
    add_calendar_features,
    build_feature_matrix,
    generate_full_grid,
)
from ml.training.tram.models import (
    fit_final_and_predict,
    train_validation_models,
)
from ml.training.tram.submission import (
    format_submission,
    generate_candidate_path,
    save_submission,
)

__all__ = [
    "ALL_ROUTES",
    "ACTIVE_ROUTES",
    "FEATURE_COLS",
    "CATEGORICAL_FEATURES",
    "generate_full_grid",
    "add_calendar_features",
    "build_feature_matrix",
    "BASE_PROFILE_COL",
    "calculate_historical_profiles",
    "attach_historical_profiles",
    "predict_seasonal_baseline",
    "compute_wape_metrics",
    "evaluate_by_route",
    "format_evaluation_report",
    "train_validation_models",
    "fit_final_and_predict",
    "format_submission",
    "save_submission",
    "generate_candidate_path",
]
