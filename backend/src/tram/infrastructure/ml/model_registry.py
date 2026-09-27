"""Read model bundle metadata without deserializing the estimator."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ARTIFACTS = ("estimator.joblib", "features.json", "config.json", "metrics.json")
MAX_METADATA_BYTES = 1024 * 1024
VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class InvalidModelBundle(Exception):
    pass


def valid_version(version: str) -> bool:
    return bool(VERSION_PATTERN.fullmatch(version))


def _read_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise InvalidModelBundle(f"missing or unsafe {path.name}")
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_METADATA_BYTES + 1)
    except OSError as exc:
        raise InvalidModelBundle(f"unreadable {path.name}") from exc
    if len(content) > MAX_METADATA_BYTES:
        raise InvalidModelBundle(f"oversized {path.name}")
    return content


def _read_json(path: Path) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    try:
        value = json.loads(_read_file(path).decode("utf-8"), object_pairs_hook=unique)
        json.dumps(value, allow_nan=False)
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        raise InvalidModelBundle(f"invalid {path.name}") from exc
    if not isinstance(value, dict):
        raise InvalidModelBundle(f"invalid {path.name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(65536):
                digest.update(chunk)
    except OSError as exc:
        raise InvalidModelBundle(f"unreadable {path.name}") from exc
    return digest.hexdigest()


def read_model_metadata(bundle_dir: Path) -> dict:
    """Validate a version 1.0 bundle and return only JSON/text metadata."""
    if bundle_dir.is_symlink() or not bundle_dir.is_dir() or not valid_version(bundle_dir.name):
        raise InvalidModelBundle("unsafe model version")

    manifest = _read_json(bundle_dir / "manifest.json")
    if manifest.get("version") != bundle_dir.name:
        raise InvalidModelBundle("manifest version mismatch")
    if manifest.get("format_version") != "1.0":
        raise InvalidModelBundle("unsupported format_version")
    created_at = manifest.get("created_at")
    if not isinstance(created_at, str):
        raise InvalidModelBundle("invalid created_at")
    try:
        timestamp = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise InvalidModelBundle("invalid created_at") from exc
    if timestamp.tzinfo is None:
        raise InvalidModelBundle("invalid created_at")
    if manifest.get("estimator_file") != "estimator.joblib":
        raise InvalidModelBundle("invalid estimator_file")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(ARTIFACTS):
        raise InvalidModelBundle("invalid artifact list")
    checksums = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise InvalidModelBundle("invalid artifact list")
        filename, checksum = artifact.get("file"), artifact.get("sha256")
        if filename not in ARTIFACTS or not isinstance(checksum, str):
            raise InvalidModelBundle("invalid artifact list")
        if filename in checksums or not SHA256_PATTERN.fullmatch(checksum):
            raise InvalidModelBundle("invalid artifact list")
        checksums[filename] = checksum
    if set(checksums) != set(ARTIFACTS):
        raise InvalidModelBundle("invalid artifact list")
    if manifest.get("estimator_sha256") != checksums["estimator.joblib"]:
        raise InvalidModelBundle("invalid estimator_sha256")
    estimator_size = manifest.get("estimator_size_bytes")
    if type(estimator_size) is not int or estimator_size < 0:
        raise InvalidModelBundle("invalid estimator_size_bytes")

    for filename in ARTIFACTS:
        path = bundle_dir / filename
        if path.is_symlink() or not path.is_file():
            raise InvalidModelBundle(f"missing or unsafe {filename}")
        if _sha256(path) != checksums[filename]:
            raise InvalidModelBundle(f"checksum mismatch: {filename}")
    try:
        actual_size = (bundle_dir / "estimator.joblib").stat().st_size
    except OSError as exc:
        raise InvalidModelBundle("unreadable estimator.joblib") from exc
    if actual_size != estimator_size:
        raise InvalidModelBundle("estimator size mismatch")

    features = _read_json(bundle_dir / "features.json")
    if not isinstance(features.get("feature_cols"), list) or not all(
        isinstance(name, str) and name for name in features["feature_cols"]
    ):
        raise InvalidModelBundle("invalid features.json")
    if not isinstance(features.get("categorical_features"), list) or not all(
        isinstance(name, str) and name for name in features["categorical_features"]
    ):
        raise InvalidModelBundle("invalid features.json")
    if not isinstance(features.get("base_profile_col"), str):
        raise InvalidModelBundle("invalid features.json")
    if not isinstance(features.get("route_categorical_features"), list) or not all(
        isinstance(name, str) and name for name in features["route_categorical_features"]
    ):
        raise InvalidModelBundle("invalid features.json")

    config = _read_json(bundle_dir / "config.json")
    if not isinstance(config.get("model_type"), str) or not config["model_type"]:
        raise InvalidModelBundle("invalid config.json")
    metrics = _read_json(bundle_dir / "metrics.json")
    try:
        card = _read_file(bundle_dir / "model-card.md").decode("utf-8")
    except UnicodeError as exc:
        raise InvalidModelBundle("invalid model-card.md") from exc
    if not card.strip():
        raise InvalidModelBundle("invalid model-card.md")

    return {"config": config, "metrics": metrics, "card": card, "checksums": checksums}


def read_active_pointer(models_root: Path) -> tuple[str | None, str | None]:
    """Return (active version, error) from models_root/active_version.txt.

    (None, None) means no pointer exists: no bundle is configured.
    """
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
