"""Read-only model registry responses."""

from pathlib import Path

from tram.application.errors import ApplicationError
from tram.infrastructure.ml.model_registry import (
    InvalidModelBundle,
    read_model_metadata,
    valid_version,
)


def _active_version(models_root: Path) -> tuple[str | None, str | None]:
    path = models_root / "active_version.txt"
    if path.is_symlink():
        return None, "unsafe active_version.txt"
    if not path.exists():
        return None, None
    try:
        with path.open("rb") as stream:
            content = stream.read(257)
    except OSError:
        return None, "unreadable active_version.txt"
    if len(content) > 256:
        return None, "invalid active_version.txt"
    try:
        version = content.decode("utf-8").strip()
    except UnicodeError:
        return None, "invalid active_version.txt"
    if not valid_version(version):
        return None, "invalid active_version.txt"
    return version, None


def _summary(version: str, active_version: str | None, metadata: dict) -> dict:
    config = metadata["config"]
    return {
        "id": version,
        "version": version,
        "method": config["model_type"],
        "is_active": version == active_version,
        "is_baseline": config["model_type"] == "baseline",
        "metrics": metadata["metrics"],
        "status": "available",
    }


def _invalid_summary(version: str, active_version: str | None, error: str) -> dict:
    return {
        "id": version,
        "version": version,
        "method": "unknown",
        "is_active": version == active_version,
        "is_baseline": False,
        "metrics": {},
        "status": "invalid",
        "error": error,
    }


def list_models(models_root: Path):
    active_version, pointer_error = _active_version(models_root)
    items = []
    try:
        directories = sorted(models_root.iterdir()) if models_root.exists() else []
    except OSError as exc:
        raise ApplicationError("SERVICE_UNAVAILABLE", "Model registry is unreadable") from exc
    for directory in directories:
        if directory.name == "active_version.txt" and not directory.is_dir():
            continue
        if not (directory.is_dir() or directory.is_symlink()):
            continue
        try:
            metadata = read_model_metadata(directory)
        except InvalidModelBundle as exc:
            items.append(_invalid_summary(directory.name, active_version, str(exc)))
        else:
            items.append(_summary(directory.name, active_version, metadata))
    if active_version and not any(item["id"] == active_version for item in items):
        items.append(
            _invalid_summary(active_version, active_version, "active model bundle is missing")
        )
        items.sort(key=lambda item: item["id"])
    page = {"items": items, "page": {"has_more": False, "next_cursor": None}}
    if pointer_error:
        page["active_version_error"] = pointer_error
    return page


def get_model(models_root: Path, model_id: str):
    if not model_id or model_id in (".", "..") or any(c in model_id for c in "/\\\x00"):
        raise ApplicationError("NOT_FOUND", "Model not found")
    model_dir = models_root / model_id
    if not (model_dir.is_dir() or model_dir.is_symlink()):
        raise ApplicationError("NOT_FOUND", "Model not found")
    try:
        metadata = read_model_metadata(model_dir)
    except InvalidModelBundle as exc:
        raise ApplicationError("SERVICE_UNAVAILABLE", f"Model bundle is invalid: {exc}") from exc
    active_version, pointer_error = _active_version(models_root)
    detail = {
        **_summary(model_id, active_version, metadata),
        "config": metadata["config"],
        "card": metadata["card"],
    }
    if pointer_error:
        detail["active_version_error"] = pointer_error
    return detail
