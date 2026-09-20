import copy
import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from tram.application.errors import ApplicationError
from tram.application.mapping import spatial_from_document
from tram.application.ports import Clock, CursorCodec, Document, Repository
from tram.domain.time import (
    MOSCOW,
    Horizon,
    Interval,
    Resolution,
    advance,
    aligned,
    forecast_window,
    parse_time,
)


def required(value, resource="Resource"):
    if value is None:
        raise ApplicationError("NOT_FOUND", f"{resource} not found")
    return value


class ReadService:
    def __init__(self, repository: Repository, clock: Clock, cursors: CursorCodec):
        self.repository, self.clock, self.cursors = repository, clock, cursors

    def dataset(self, revision=None):
        result = self.repository.dataset(revision)
        if result is None and revision is None:
            raise ApplicationError("SERVICE_UNAVAILABLE", "No published dataset is available")
        return required(result, "Dataset revision")

    def network(self, revision):
        return required(self.repository.network(revision), "Network revision")

    def paginate(self, scope, query, fetch):
        filters = {k: v for k, v in query.items() if k != "cursor"}
        fingerprint = hashlib.sha256(
            json.dumps([scope, filters], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        now = self.clock.now()
        if query.get("cursor"):
            state = self.cursors.decode(query["cursor"])
            if state.get("fingerprint") != fingerprint or parse_time(state["expires_at"]) <= now:
                raise ApplicationError(
                    "INVALID_CURSOR", "Cursor expired or does not match the request"
                )
        else:
            state = {
                "fingerprint": fingerprint,
                "offset": 0,
                "before": now.isoformat(),
                "expires_at": (now + timedelta(hours=1)).isoformat(),
            }
        limit = query.get("limit", 200)
        rows = fetch(state["offset"], limit + 1, parse_time(state["before"]))
        more = len(rows) > limit
        cursor = self.cursors.encode({**state, "offset": state["offset"] + limit}) if more else None
        return rows[:limit], {"next_cursor": cursor, "has_more": more}

    def capabilities(self, query):
        return self.dataset(query.get("dataset_revision_id"))["capabilities"]

    def data_status(self):
        dataset = self.repository.dataset(None)
        now = self.clock.now()
        if not dataset:
            return {
                "checked_at": now.isoformat(),
                "dataset_revision_id": None,
                "network_revision_id": None,
                "source_mode": "batch",
                "sources": [],
                "recommended_poll_seconds": 30,
                "warnings": ["No data has been published"],
            }
        capabilities = dataset["capabilities"]
        sources = copy.deepcopy(dataset["sources"])
        for source in sources:
            threshold = source["stale_after_seconds"]
            watermark = source["event_watermark"]
            source["freshness"] = (
                "unknown"
                if threshold is None or watermark is None
                else "stale"
                if (now - parse_time(watermark)).total_seconds() > threshold
                else "fresh"
            )
        return {
            "checked_at": now.isoformat(),
            "dataset_revision_id": capabilities["dataset_revision_id"],
            "network_revision_id": capabilities["network_revision_id"],
            "source_mode": capabilities["source_mode"],
            "sources": sources,
            "recommended_poll_seconds": 30,
            "warnings": capabilities["warnings"],
        }

    @staticmethod
    def active_routes(network, date):
        return [
            r
            for r in network["routes"]
            if r["route"]["valid_from"] <= date
            and (r["route"]["valid_to"] is None or date < r["route"]["valid_to"])
        ]

    def routes(self, query):
        network = self.network(query["network_revision_id"])
        routes = sorted(
            (r["route"] for r in self.active_routes(network, query["valid_at"])),
            key=lambda r: r["id"],
        )
        items, page = self.paginate(
            "routes", query, lambda offset, limit, _: routes[offset : offset + limit]
        )
        return {
            "network_revision_id": query["network_revision_id"],
            "valid_at": query["valid_at"],
            "items": items,
            "page": page,
        }

    def route(self, route_id, query):
        network = self.network(query["network_revision_id"])
        route = required(
            next(
                (
                    r
                    for r in self.active_routes(network, query["valid_at"])
                    if r["route"]["id"] == route_id
                ),
                None,
            ),
            "Route on requested date",
        )
        return {**route, "valid_at": query["valid_at"]}

    def stops(self, query):
        network = self.network(query["network_revision_id"])
        routes = self.active_routes(network, query["valid_at"])
        if query.get("direction_id") and not query.get("route_id"):
            raise ApplicationError(
                "VALIDATION_ERROR", "direction_id requires route_id", "direction_id"
            )
        if query.get("route_id"):
            routes = [self.route(query["route_id"], query)]
        stop_map = {}
        for route in routes:
            directions = route["directions"]
            if query.get("direction_id"):
                directions = [
                    required(
                        next((d for d in directions if d["id"] == query["direction_id"]), None),
                        "Direction",
                    )
                ]
            ids = {s["stop_id"] for d in directions for s in d["stops"]}
            stop_map.update({s["id"]: s for s in route["stops"] if s["id"] in ids})
        stops = sorted(stop_map.values(), key=lambda s: s["id"])
        items, page = self.paginate(
            "stops", query, lambda offset, limit, _: stops[offset : offset + limit]
        )
        return {
            "network_revision_id": query["network_revision_id"],
            "valid_at": query["valid_at"],
            "items": items,
            "page": page,
        }

    @staticmethod
    def validate_spatial(network, profile, query):
        route_id = query.get("route_id")
        dimensions = ("direction_id", "stop_id", "stop_sequence", "segment_id")
        if any(query.get(k) is not None for k in dimensions) and not route_id:
            raise ApplicationError("VALIDATION_ERROR", "Spatial filters require route_id")
        if query.get("stop_sequence") is not None and not query.get("stop_id"):
            raise ApplicationError("VALIDATION_ERROR", "stop_sequence requires stop_id")
        level = profile["spatial_level"]
        if (
            ((query.get("stop_id") or query.get("stop_sequence")) and level != "stop")
            or (query.get("segment_id") and level != "segment")
            or (query.get("direction_id") and level == "route")
        ):
            raise ApplicationError(
                "UNSUPPORTED_PROFILE", "Spatial filters do not match the profile"
            )
        if not route_id:
            return
        route = required(
            next((r for r in network["routes"] if r["route"]["id"] == route_id), None), "Route"
        )
        if route_id not in profile["route_ids"]:
            raise ApplicationError("UNSUPPORTED_PROFILE", "Route is unavailable in this profile")
        directions = route["directions"]
        if query.get("direction_id"):
            selected = [d for d in directions if d["id"] == query["direction_id"]]
            if not selected:
                known = any(
                    d["id"] == query["direction_id"]
                    for r in network["routes"]
                    for d in r["directions"]
                )
                raise ApplicationError(
                    "VALIDATION_ERROR" if known else "NOT_FOUND",
                    "Direction does not belong to the selected route",
                )
            directions = selected
        if query.get("stop_id"):
            known = any(s["id"] == query["stop_id"] for r in network["routes"] for s in r["stops"])
            if not known:
                raise ApplicationError("NOT_FOUND", "Stop not found")
            if not any(
                s["stop_id"] == query["stop_id"]
                and (query.get("stop_sequence") is None or s["sequence"] == query["stop_sequence"])
                for d in directions
                for s in d["stops"]
            ):
                raise ApplicationError(
                    "VALIDATION_ERROR",
                    "Stop position does not belong to the selected route/direction",
                )
        if query.get("segment_id"):
            known = any(
                s["id"] == query["segment_id"]
                for r in network["routes"]
                for d in r["directions"]
                for s in d["segments"]
            )
            if not known:
                raise ApplicationError("NOT_FOUND", "Segment not found")
            if not any(s["id"] == query["segment_id"] for d in directions for s in d["segments"]):
                raise ApplicationError(
                    "VALIDATION_ERROR", "Segment does not belong to selected route/direction"
                )

    def observations(self, query):
        dataset = self.dataset(query["dataset_revision_id"])
        capabilities = dataset["capabilities"]
        profile = required(
            next(
                (
                    p
                    for p in capabilities["observation_profiles"]
                    if p["id"] == query["observation_profile_id"]
                ),
                None,
            ),
            "Observation profile",
        )
        Interval(parse_time(query["from"]), parse_time(query["to"])).validate_grid(
            Resolution(profile["resolution"])
        )
        self.validate_spatial(self.network(capabilities["network_revision_id"]), profile, query)
        items, page = self.paginate(
            "observations",
            query,
            lambda offset, limit, _: self.repository.observation_points(
                query["dataset_revision_id"], profile["id"], query, offset, limit
            ),
        )
        return {
            "dataset_revision_id": capabilities["dataset_revision_id"],
            "network_revision_id": capabilities["network_revision_id"],
            "source_mode": capabilities["source_mode"],
            "profile": profile,
            "items": items,
            "page": page,
        }

    def get_run(self, run_id):
        return required(self.repository.run(run_id), "Forecast run")

    def runs(self, query):
        if query.get("dataset_revision_id"):
            self.dataset(query["dataset_revision_id"])
        items, page = self.paginate(
            "runs",
            query,
            lambda offset, limit, before: self.repository.runs(query, before, offset, limit),
        )
        return {"items": items, "page": page}

    def ready_run(self, run_id, query):
        run = self.get_run(run_id)
        if run["status"] != "succeeded":
            raise ApplicationError(
                "RUN_FAILED" if run["status"] == "failed" else "RESULT_NOT_READY",
                "Forecast results are unavailable",
            )
        self.validate_spatial(self.network(run["network_revision_id"]), run["profile"], query)
        if query.get("route_id") and query["route_id"] not in run["route_ids"]:
            raise ApplicationError("VALIDATION_ERROR", "Route is outside the forecast scope")
        return run

    def points(self, run_id, query):
        run = self.ready_run(run_id, query)
        window = Interval(parse_time(query["from"]), parse_time(query["to"]))
        window.validate_grid(Resolution(run["profile"]["resolution"]))
        if window.start < parse_time(run["forecast_start"]) or window.end > parse_time(
            run["forecast_end"]
        ):
            raise ApplicationError(
                "VALIDATION_ERROR", "Requested interval is outside the forecast period"
            )
        items, page = self.paginate(
            f"points:{run_id}",
            query,
            lambda offset, limit, _: self.repository.forecast_points(run_id, query, offset, limit),
        )
        return {"run": run, "items": items, "page": page}

    def map(self, run_id, query):
        run = self.ready_run(run_id, query)
        start = parse_time(query["interval_start"])
        resolution = Resolution(run["profile"]["resolution"])
        if not aligned(start, resolution) or not parse_time(
            run["forecast_start"]
        ) <= start < parse_time(run["forecast_end"]):
            raise ApplicationError(
                "VALIDATION_ERROR", "interval_start must identify a forecast interval"
            )
        items, page = self.paginate(
            f"map:{run_id}",
            query,
            lambda offset, limit, _: self.repository.forecast_points(run_id, query, offset, limit),
        )
        series = self.repository.series(
            run["dataset_revision_id"], run["profile"]["observation_profile_id"], run["route_ids"]
        )
        geometries = {spatial_from_document(s["spatial"]).canonical: s["geometry"] for s in series}
        features = []
        for point in items:
            key = spatial_from_document(point["spatial"]).canonical
            geometry = geometries.get(key)
            point = copy.deepcopy(point)
            if geometry is None:
                point["quality"]["flags"] = sorted(
                    set(point["quality"]["flags"] + ["missing_geometry"])
                )
            features.append(
                {
                    "type": "Feature",
                    "id": hashlib.sha256(
                        f"{run_id}:{key}:{point['interval_start']}".encode()
                    ).hexdigest(),
                    "geometry": geometry,
                    "properties": point,
                }
            )
        return {
            "type": "FeatureCollection",
            "features": features,
            "run": run,
            "interval_start": start.isoformat(),
            "interval_end": advance(start, resolution).isoformat(),
            "page": page,
        }

    def evaluations(self, query):
        if query.get("dataset_revision_id"):
            self.dataset(query["dataset_revision_id"])
        items, page = self.paginate(
            "evaluations",
            query,
            lambda offset, limit, before: self.repository.evaluations(query, before, offset, limit),
        )
        return {"items": items, "page": page}

    def evaluation(self, evaluation_id):
        return required(self.repository.evaluation(evaluation_id), "Evaluation report")

    def evaluation_points(self, evaluation_id, query):
        report = self.evaluation(evaluation_id)
        summary = report["summary"]
        Interval(parse_time(query["from"]), parse_time(query["to"])).validate_grid(
            Resolution(summary["profile"]["resolution"])
        )
        self.validate_spatial(
            self.network(summary["network_revision_id"]), summary["profile"], query
        )
        if query.get("fold_id") and query["fold_id"] not in {f["id"] for f in report["folds"]}:
            raise ApplicationError("NOT_FOUND", "Evaluation fold not found")
        items, page = self.paginate(
            f"evaluation-points:{evaluation_id}",
            query,
            lambda offset, limit, _: self.repository.evaluation_points(
                evaluation_id, query, offset, limit
            ),
        )
        return {"summary": summary, "items": items, "page": page}


class ForecastService:
    def __init__(self, repository: Repository, clock: Clock, reads: ReadService):
        self.repository, self.clock, self.reads = repository, clock, reads

    def create(self, command: Document, owner: str, idempotency_key: str):
        now = self.clock.now()
        fingerprint = hashlib.sha256(
            json.dumps(command, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        replay = self.repository.replay_run(owner, idempotency_key, fingerprint, now)
        if replay:
            return replay, False
        dataset = self.reads.dataset(command["dataset_revision_id"])
        caps = dataset["capabilities"]
        profile = required(
            next((p for p in caps["forecast_profiles"] if p["id"] == command["profile_id"]), None),
            "Forecast profile",
        )
        if profile["availability"] != "available":
            raise ApplicationError(
                "UNSUPPORTED_PROFILE", profile["unavailable_reason"] or "Profile unavailable"
            )
        as_of, start = parse_time(command["as_of"]), parse_time(command["forecast_start"])
        if as_of > now or as_of > start:
            raise ApplicationError(
                "VALIDATION_ERROR", "as_of must not be in the future or after forecast_start"
            )
        for value, lower, upper in (
            (as_of, "allowed_as_of_start", "allowed_as_of_end"),
            (start, "forecast_start_min", "forecast_start_max"),
        ):
            if (
                not profile[lower]
                or not profile[upper]
                or not parse_time(profile[lower]) <= value <= parse_time(profile[upper])
            ):
                raise ApplicationError(
                    "UNSUPPORTED_PROFILE", "Date is outside the profile's supported range"
                )
        window = forecast_window(
            start, Horizon(profile["horizon"]), Resolution(profile["resolution"])
        )
        network = self.reads.network(caps["network_revision_id"])
        for route in command["route_ids"]:
            self.reads.validate_spatial(network, profile, {"route_id": route})
            summary = next(r["route"] for r in network["routes"] if r["route"]["id"] == route)
            if summary["valid_from"] > window.start.astimezone(MOSCOW).date().isoformat() or (
                summary["valid_to"] is not None
                and summary["valid_to"] < window.end.astimezone(MOSCOW).date().isoformat()
            ):
                raise ApplicationError(
                    "UNSUPPORTED_PROFILE", "Route is not valid throughout the forecast period"
                )
        candidates = [
            m["model"]
            for m in dataset["models"]
            if profile["id"] in m["profile_ids"]
            and m["model"]["method"] == "seasonal_naive_v1"
            and parse_time(m["model"]["training_history_end"]) <= as_of
        ]
        if not candidates:
            raise ApplicationError("MODEL_UNAVAILABLE", "No supported model is available at as_of")
        model = max(
            candidates, key=lambda m: (parse_time(m["training_history_end"]), m["id"], m["version"])
        )
        observed = required(
            next(
                (
                    p
                    for p in caps["observation_profiles"]
                    if p["id"] == profile["observation_profile_id"]
                ),
                None,
            ),
            "Observation profile",
        )
        series = self.repository.series(
            caps["dataset_revision_id"], observed["id"], command["route_ids"]
        )
        if {s["spatial"]["route_id"] for s in series} != set(command["route_ids"]):
            raise ApplicationError(
                "INSUFFICIENT_HISTORY", "One or more routes have no prepared series"
            )
        run = {
            "id": str(uuid4()),
            "status": "queued",
            "dataset_revision_id": caps["dataset_revision_id"],
            "network_revision_id": caps["network_revision_id"],
            "profile": profile,
            "route_ids": command["route_ids"],
            "source_mode": caps["source_mode"],
            "timezone": "Europe/Moscow",
            "as_of": as_of.isoformat(),
            "history_end": min(parse_time(observed["history_end"]), as_of).isoformat(),
            "forecast_start": window.start.isoformat(),
            "forecast_end": window.end.isoformat(),
            "model": model,
            "created_at": now.isoformat(),
            "started_at": None,
            "calculated_at": None,
            "finished_at": None,
            "point_count": 0,
            "quality": {"status": "unverified", "coverage_ratio": None, "flags": []},
            "warnings": ["Seasonal baseline; no model training was performed"],
            "failure": None,
        }
        return self.repository.create_run(owner, idempotency_key, fingerprint, run, now)
