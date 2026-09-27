"""Describe the configured model bundle for run creation and readiness.

Only JSON/text metadata and checksums are read (via model_registry); the
estimator is never deserialized here, so the API process does not load
pickled code. The result is cached until a bundle file or the active pointer
changes, which keeps /health cheap despite hashing the estimator.
"""

import copy
import importlib.util
from pathlib import Path

from tram.application.models import BUNDLE_METHOD
from tram.domain.errors import DomainError
from tram.domain.time import parse_time
from tram.infrastructure.ml.model_registry import (
    ARTIFACTS,
    InvalidModelBundle,
    read_active_pointer,
    read_model_metadata,
    valid_version,
)

# Route numbers of the competition network; mirrors ml.training.tram.features.ALL_ROUTES
# so the API does not import pandas. tests/test_model_selection.py asserts they match.
DEFAULT_BUNDLE_ROUTES = (1, 5, 7, 11, 12, 17, 25, 26, 28, 50)

# Library the worker needs to unpickle each model type (see pyproject [training] extra).
MODEL_LIBRARIES = {"catboost": "catboost", "lightgbm": "lightgbm", "histgradient": "sklearn"}

NOT_CONFIGURED = {
    "status": "not_configured",
    "version": None,
    "reason": None,
    "model": None,
    "routes": [],
}


def _invalid(version, reason):
    return {"status": "invalid", "version": version, "reason": reason, "model": None, "routes": []}


class FileModelCatalog:
    """ModelCatalog backed by models/tram/<version>/ and active_version.txt.

    ``configured_version`` (TRAM_MODEL_VERSION) takes precedence over the
    active pointer, matching how the worker chooses the bundle to load.
    """

    def __init__(self, models_root: Path, configured_version: str | None = None):
        self.models_root = Path(models_root)
        self.configured_version = configured_version or None
        self._cache_key = None
        self._cache_value = None

    def _signature(self, version):
        bundle_dir = self.models_root / version
        parts = [version]
        for name in (*ARTIFACTS, "manifest.json", "model-card.md"):
            try:
                stat = (bundle_dir / name).stat()
                parts.append((name, stat.st_mtime_ns, stat.st_size))
            except OSError:
                parts.append((name, None, None))
        return tuple(parts)

    def active_bundle(self):
        if self.configured_version:
            version = self.configured_version
            if not valid_version(version):
                return _invalid(None, "invalid TRAM_MODEL_VERSION")
        else:
            version, error = read_active_pointer(self.models_root)
            if error:
                return _invalid(None, error)
            if version is None:
                return copy.deepcopy(NOT_CONFIGURED)
        key = self._signature(version)
        if key != self._cache_key:
            self._cache_value = self._describe(version)
            self._cache_key = key
        return copy.deepcopy(self._cache_value)

    def _describe(self, version):
        try:
            metadata = read_model_metadata(self.models_root / version)
        except InvalidModelBundle as exc:
            return _invalid(version, str(exc))
        config = metadata["config"]
        model_type = config["model_type"]
        library = MODEL_LIBRARIES.get(model_type)
        if library and importlib.util.find_spec(library) is None:
            return _invalid(
                version,
                f"model_type {model_type} needs the {library} package, which is not installed",
            )
        training_history_end = config.get("training_history_end")
        try:
            if not isinstance(training_history_end, str):
                raise DomainError("missing")
            history_end = parse_time(training_history_end)
        except DomainError:
            return _invalid(
                version, "config.json has no RFC 3339 training_history_end with an offset"
            )
        routes = config.get("routes", DEFAULT_BUNDLE_ROUTES)
        if not isinstance(routes, list | tuple) or not all(
            type(route) is int or (isinstance(route, str) and route) for route in routes
        ):
            return _invalid(version, "config.json routes must be a list of route numbers")
        return {
            "status": "ok",
            "version": version,
            "reason": None,
            "routes": [str(route) for route in routes],
            "model_type": model_type,
            "model": {
                "id": version,
                "version": version,
                "method": BUNDLE_METHOD,
                "training_history_end": history_end.isoformat(),
                "feature_set_version": "features-" + metadata["checksums"]["features.json"][:12],
                "is_baseline": model_type == "baseline",
            },
        }
