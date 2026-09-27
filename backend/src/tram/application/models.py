"""Choose the model pinned to a forecast run.

The model is decided once, when the run is created, and stored in the run.
The worker executes exactly that model and never substitutes another one:
a run that says ``seasonal_naive_v1`` must have been computed by the seasonal
baseline, and a run that names a bundle version must have been computed by
that version. See docs/decisions/0004-model-selection-and-fallback.md.
"""

from datetime import datetime

from tram.application.errors import ApplicationError
from tram.application.ports import Document
from tram.domain.time import parse_time

SEASONAL_METHOD = "seasonal_naive_v1"
BUNDLE_METHOD = "tram_bundle"
SEASONAL_WARNING = "Seasonal baseline; no model training was performed"


def _seasonal_model(dataset_models: list[Document], profile_id: str, as_of: datetime):
    candidates = [
        m["model"]
        for m in dataset_models
        if profile_id in m["profile_ids"]
        and m["model"]["method"] == SEASONAL_METHOD
        and parse_time(m["model"]["training_history_end"]) <= as_of
    ]
    if not candidates:
        return None
    return max(
        candidates, key=lambda m: (parse_time(m["training_history_end"]), m["id"], m["version"])
    )


def _bundle_ineligibility(bundle: Document, profile: Document, route_ids, as_of: datetime):
    """Why an otherwise valid bundle cannot serve this run, or None if it can."""
    if profile["resolution"] != "hour":
        return f"profile resolution is {profile['resolution']}, the bundle forecasts hourly values"
    level = profile.get("spatial_level", "route")
    if level != "route":
        return f"profile spatial level is {level}, the bundle forecasts route totals"
    unsupported = [route for route in route_ids if route not in bundle["routes"]]
    if unsupported:
        return f"route {unsupported[0]} is not a route number supported by the bundle"
    if parse_time(bundle["model"]["training_history_end"]) > as_of:
        return (
            f"the bundle was trained on data up to {bundle['model']['training_history_end']}, "
            "which is after as_of"
        )
    return None


def select_model(
    *,
    profile: Document,
    route_ids: list[str],
    as_of: datetime,
    dataset_models: list[Document],
    bundle: Document,
    fallback_to_seasonal_naive: bool,
) -> tuple[Document, list[str]]:
    """Return (ModelReference, run warnings).

    ``bundle`` is the document returned by ModelCatalog.active_bundle():
    status ``not_configured`` (no bundle is expected), ``ok`` (valid and
    loadable metadata) or ``invalid`` (a bundle is configured but unusable).
    """
    status = bundle["status"]
    if status == "ok":
        reason = _bundle_ineligibility(bundle, profile, route_ids, as_of)
        if reason is None:
            warnings = []
            if bundle["model"]["is_baseline"]:
                warnings.append(
                    f"Model bundle {bundle['version']} is a seasonal-profile baseline; "
                    "no model was fitted"
                )
            return bundle["model"], warnings
        bundle_warning = f"Model bundle {bundle['version']} is not used: {reason}"
    elif status == "invalid":
        if not fallback_to_seasonal_naive and profile["resolution"] == "hour":
            raise ApplicationError(
                "MODEL_UNAVAILABLE",
                f"Configured model bundle is invalid ({bundle['reason']}); "
                "fallback to the seasonal baseline is disabled",
            )
        name = f"model bundle {bundle['version']}" if bundle["version"] else "model bundle"
        bundle_warning = f"Configured {name} is invalid and was not used: {bundle['reason']}"
    else:
        bundle_warning = None

    model = _seasonal_model(dataset_models, profile["id"], as_of)
    if model is None:
        raise ApplicationError("MODEL_UNAVAILABLE", "No supported model is available at as_of")
    warnings = [SEASONAL_WARNING]
    if bundle_warning:
        warnings.append(bundle_warning)
    return model, warnings


def model_readiness(bundle: Document, fallback_to_seasonal_naive: bool) -> Document:
    """Readiness of model serving for /health.

    not_configured: no bundle is expected; the seasonal baseline is the model.
    ok: the configured bundle is valid.
    fallback: the configured bundle is invalid, new runs use the seasonal baseline.
    invalid: the configured bundle is invalid and fallback is disabled — not ready.
    """
    status = bundle["status"]
    if status == "invalid":
        state = "fallback" if fallback_to_seasonal_naive else "invalid"
    else:
        state = status
    return {"model": state, "model_version": bundle["version"], "ready": state != "invalid"}
