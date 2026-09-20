"""Semantic validation of prepared, versioned observations (no raw-data ETL)."""

from collections.abc import Iterable
from typing import Protocol

from tram.application.errors import ApplicationError
from tram.application.mapping import spatial_from_document
from tram.application.ports import Clock, Document
from tram.application.service import ReadService
from tram.domain.series import Observation
from tram.domain.time import Horizon, Interval, Resolution, advance, forecast_window, parse_time


class DatasetWriter(Protocol):
    def publish(self, manifest: Document, records: Iterable[Document], now) -> bool: ...


def require(condition, message):
    if not condition:
        raise ApplicationError("VALIDATION_ERROR", message)


def unique(items, key="id"):
    indexed = {item[key]: item for item in items}
    require(len(indexed) == len(items), f"Duplicate {key}")
    return indexed


class PublishDataset:
    def __init__(self, writer: DatasetWriter, clock: Clock):
        self.writer, self.clock = writer, clock

    def execute(self, manifest, records):
        caps, network = manifest["capabilities"], manifest["network"]
        require(network["id"] == caps["network_revision_id"], "Network revision mismatch")
        routes = unique([r["route"] for r in network["routes"]])
        require(bool(routes), "Network must contain routes")
        shared_stops = {}
        for route in network["routes"]:
            require(route["network_revision_id"] == network["id"], "Route network mismatch")
            summary = route["route"]
            require(
                summary["valid_to"] is None or summary["valid_from"] < summary["valid_to"],
                "Invalid route validity",
            )
            stops = unique(route["stops"])
            unique(route["directions"])
            for key, stop in stops.items():
                require(
                    key not in shared_stops or shared_stops[key] == stop, "Conflicting shared stop"
                )
                shared_stops[key] = stop
            for direction in route["directions"]:
                positions = unique(direction["stops"], "sequence")
                require(
                    all(p["stop_id"] in stops for p in positions.values()), "Unknown direction stop"
                )
                unique(direction["segments"])
                for segment in direction["segments"]:
                    for side in ("from", "to"):
                        position = positions.get(segment[f"{side}_sequence"])
                        require(
                            position is not None
                            and position["stop_id"] == segment[f"{side}_stop_id"],
                            "Segment endpoint mismatch",
                        )
        observations = unique(caps["observation_profiles"])
        forecasts = unique(caps["forecast_profiles"])
        require(bool(observations), "At least one observation profile is required")
        units = {
            "validations": "validations",
            "boardings": "passengers",
            "occupancy": "passengers",
            "occupancy_ratio": "ratio",
        }
        for profile in observations.values():
            require(profile["unit"] == units[profile["metric"]], "Metric/unit mismatch")
            require(set(profile["route_ids"]) <= routes.keys(), "Unknown profile route")
            Interval(
                parse_time(profile["history_start"]), parse_time(profile["history_end"])
            ).validate_grid(Resolution(profile["resolution"]), max_days=36600)
        for profile in forecasts.values():
            observed = observations.get(profile["observation_profile_id"])
            require(observed is not None, "Unknown observation profile")
            require(
                all(
                    profile[k] == observed[k]
                    for k in ("metric", "unit", "spatial_level", "resolution", "aggregation_method")
                ),
                "Forecast/history profiles disagree",
            )
            require(
                set(profile["route_ids"]) <= set(observed["route_ids"]),
                "Forecast routes outside observation profile",
            )
            require(
                profile["prediction_interval_available"] is False,
                "Seasonal baseline has no calibrated prediction intervals",
            )
            require(
                profile["start_alignment"]
                == ("month_start" if profile["horizon"] == "year" else "local_midnight"),
                "Invalid start alignment",
            )
            if profile["availability"] == "available":
                require(
                    profile["unavailable_reason"] is None,
                    "Available profile cannot have unavailable_reason",
                )
                for lower, upper in (
                    ("allowed_as_of_start", "allowed_as_of_end"),
                    ("forecast_start_min", "forecast_start_max"),
                ):
                    require(
                        bool(profile[lower]) and bool(profile[upper]),
                        "Available profile requires date bounds",
                    )
                    require(
                        parse_time(profile[lower]) <= parse_time(profile[upper]),
                        "Reversed profile date bounds",
                    )
                forecast_window(
                    parse_time(profile["forecast_start_min"]),
                    Horizon(profile["horizon"]),
                    Resolution(profile["resolution"]),
                )
                forecast_window(
                    parse_time(profile["forecast_start_max"]),
                    Horizon(profile["horizon"]),
                    Resolution(profile["resolution"]),
                )
            else:
                require(
                    bool(profile["unavailable_reason"]), "Unavailable profile requires a reason"
                )
        model_keys, covered = set(), set()
        for entry in manifest["models"]:
            model = entry["model"]
            key = (model["id"], model["version"])
            require(key not in model_keys, "Duplicate model version")
            model_keys.add(key)
            require(
                model["method"] == "seasonal_naive_v1" and model["is_baseline"],
                "Only the untrained seasonal baseline is supported",
            )
            require(
                bool(entry["profile_ids"]) and set(entry["profile_ids"]) <= forecasts.keys(),
                "Unknown model profile",
            )
            require(
                parse_time(model["training_history_end"]) <= self.clock.now(),
                "Model history cutoff is in the future",
            )
            covered.update(entry["profile_ids"])
        require(
            all(p["id"] in covered for p in forecasts.values() if p["availability"] == "available"),
            "Available forecast profile has no model",
        )
        unique(manifest["sources"], "source")
        require(
            all(s["source_mode"] == caps["source_mode"] for s in manifest["sources"]),
            "Mixed source modes are not supported in one revision",
        )
        series, next_start, route_coverage = {}, {}, {key: set() for key in observations}
        for item in manifest["series"]:
            spatial = spatial_from_document(item["spatial"])
            profile = observations.get(item["profile_id"])
            require(profile is not None, "Unknown series profile")
            require(
                spatial.level.value == profile["spatial_level"], "Series spatial level mismatch"
            )
            ReadService.validate_spatial(network, profile, item["spatial"])
            key = (item["profile_id"], spatial.canonical)
            require(key not in series, "Duplicate series")
            coverage = Interval(
                parse_time(item["coverage_start"]), parse_time(item["coverage_end"])
            )
            coverage.validate_grid(Resolution(profile["resolution"]), max_days=36600)
            require(
                parse_time(profile["history_start"])
                <= coverage.start
                < coverage.end
                <= parse_time(profile["history_end"]),
                "Series outside profile history",
            )
            if item["geometry"] is not None:
                require(
                    (item["geometry"]["type"] == "Point") == (spatial.level.value == "stop"),
                    "Series geometry type mismatch",
                )
            series[key], next_start[key] = item, coverage.start
            route_coverage[item["profile_id"]].add(spatial.route_id)
        require(
            all(route_coverage[k] == set(p["route_ids"]) for k, p in observations.items()),
            "Profile has routes without prepared series",
        )

        def validated_records():
            for record in records:
                point = record["point"]
                spatial = spatial_from_document(point["spatial"])
                key = (record["profile_id"], spatial.canonical)
                require(key in series, "Observation references an undeclared series")
                item, profile = series[key], observations[record["profile_id"]]
                interval = Interval(
                    parse_time(point["interval_start"]), parse_time(point["interval_end"])
                )
                resolution = Resolution(profile["resolution"])
                interval.validate_grid(resolution)
                require(
                    advance(interval.start, resolution) == interval.end,
                    "Observation must cover exactly one bucket",
                )
                require(
                    interval.start == next_start[key],
                    "Duplicate, unordered or missing bucket; represent gaps with null",
                )
                require(
                    interval.end <= parse_time(item["coverage_end"]),
                    "Observation exceeds series coverage",
                )
                observation = Observation(
                    spatial, interval, parse_time(record["available_at"]), point["value"]
                )
                require(
                    observation.available_at <= self.clock.now(),
                    "Observation availability is in the future",
                )
                next_start[key] = interval.end
                yield record
            require(
                all(
                    next_start[key] == parse_time(item["coverage_end"])
                    for key, item in series.items()
                ),
                "Incomplete observation series",
            )

        return self.writer.publish(manifest, validated_records(), self.clock.now())
