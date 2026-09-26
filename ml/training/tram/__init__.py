"""Tram ridership prediction training and feature engineering package."""

from ml.training.tram.features import (
    ALL_ROUTES,
    ACTIVE_ROUTES,
    FEATURE_COLS,
    CATEGORICAL_FEATURES,
    generate_full_grid,
    add_calendar_features,
    build_feature_matrix,
)
from ml.training.tram.baseline import (
    BASE_PROFILE_COL,
    calculate_historical_profiles,
    attach_historical_profiles,
    predict_seasonal_baseline,
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
