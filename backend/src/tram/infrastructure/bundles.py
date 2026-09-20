"""File adapter for the prepared-data interchange format."""

from tram.application.errors import ApplicationError
from tram.infrastructure.contract import strict_json


def fields(document, expected, label):
    if not isinstance(document, dict) or set(document) != set(expected.split()):
        raise ApplicationError("VALIDATION_ERROR", f"Unexpected or missing fields in {label}")


def read_bundle(directory, contract):
    manifest = strict_json((directory / "manifest.json").read_bytes())
    fields(manifest, "capabilities sources models series network", "manifest")
    for key in ("sources", "models", "series"):
        if not isinstance(manifest[key], list):
            raise ApplicationError("VALIDATION_ERROR", f"{key} must be an array")
    contract.validate("Capabilities", manifest["capabilities"])
    fields(manifest["network"], "id routes", "network")
    if not isinstance(manifest["network"]["routes"], list):
        raise ApplicationError("VALIDATION_ERROR", "network.routes must be an array")
    for route in manifest["network"]["routes"]:
        contract.validate("RouteDetail", route)
    for source in manifest["sources"]:
        contract.validate("SourceStatus", source)
    for entry in manifest["models"]:
        fields(entry, "profile_ids model", "model entry")
        contract.validator(
            {"type": "array", "items": {"type": "string"}, "uniqueItems": True, "minItems": 1}
        ).validate(entry["profile_ids"])
        contract.validate("ModelReference", entry["model"])
    for item in manifest["series"]:
        fields(item, "profile_id spatial geometry coverage_start coverage_end", "series")
        contract.validate("SpatialKey", item["spatial"])
        if item["geometry"] is not None:
            contract.validate("Geometry", item["geometry"])
        for key in ("coverage_start", "coverage_end"):
            contract.validator({"type": "string", "format": "date-time"}).validate(item[key])

    def records():
        with (directory / "observations.jsonl").open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                record = strict_json(line)
                fields(record, "profile_id available_at point", f"observation line {line_number}")
                contract.validate("ObservationPoint", record["point"])
                contract.validator({"type": "string", "format": "date-time"}).validate(
                    record["available_at"]
                )
                yield record

    return manifest, records()
