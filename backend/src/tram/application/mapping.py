from dataclasses import asdict

from tram.application.ports import Document
from tram.domain.series import SpatialKey, SpatialLevel


def spatial_from_document(value: Document) -> SpatialKey:
    return SpatialKey(
        SpatialLevel(value["level"]),
        value["route_id"],
        value.get("direction_id"),
        value.get("stop_id"),
        value.get("stop_sequence"),
        value.get("segment_id"),
    )


def spatial_document(value: SpatialKey) -> Document:
    return {**asdict(value), "level": value.level.value}
