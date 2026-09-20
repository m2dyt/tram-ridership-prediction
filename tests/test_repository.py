import copy
import unittest
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from tram.application.errors import ApplicationError
from tram.application.service import ForecastService, ReadService
from tram.application.worker import RunWorker
from tram.infrastructure.database import Base, ForecastPointRow, make_engine, session_factory
from tram.infrastructure.repository import SqlRepository, point_columns
from tram.infrastructure.runtime import SignedCursor
from tram_ml.baseline import SeasonalNaive

from tests.support import NOW, FrozenClock, seed_trusted_fixture


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.sessions = session_factory(self.engine)
        seed_trusted_fixture(self.sessions)
        self.repo = SqlRepository(self.sessions)
        self.clock = FrozenClock()
        self.reads = ReadService(self.repo, self.clock, SignedCursor("c" * 32))
        self.forecasts = ForecastService(self.repo, self.clock, self.reads)
        self.command = {
            "dataset_revision_id": "demo-data-v1",
            "profile_id": "demo-validations-stop-day-hour",
            "route_ids": ["demo-route-01"],
            "as_of": "2026-09-20T18:00:00+03:00",
            "forecast_start": "2026-09-21T00:00:00+03:00",
        }

    def tearDown(self):
        self.engine.dispose()

    def test_idempotency_and_conflict(self):
        first, created = self.forecasts.create(self.command, "operator", "test-key-1")
        second, repeated = self.forecasts.create(
            dict(reversed(list(self.command.items()))), "operator", "test-key-1"
        )
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.assertEqual(first["id"], second["id"])
        with self.assertRaises(ApplicationError) as error:
            self.forecasts.create(
                {**self.command, "forecast_start": "2026-09-22T00:00:00+03:00"},
                "operator",
                "test-key-1",
            )
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")

    def test_status_filtered_pages_keep_membership_after_worker_transition(self):
        first, _ = self.forecasts.create(self.command, "operator", "page-key-1")
        self.clock.value += timedelta(seconds=1)
        second, _ = self.forecasts.create(self.command, "operator", "page-key-2")
        self.clock.value += timedelta(seconds=1)
        query = {"status": "queued", "limit": 1}
        page = self.reads.runs(query)
        self.assertEqual(page["items"][0]["id"], second["id"])
        self.clock.value += timedelta(seconds=1)
        self.assertTrue(RunWorker(self.repo, self.clock, SeasonalNaive()).execute_one())
        following = self.reads.runs({**query, "cursor": page["page"]["next_cursor"]})
        self.assertEqual(following["items"][0]["id"], first["id"])
        self.assertEqual(following["items"][0]["status"], "succeeded")

    def test_forecast_rejects_route_expiring_inside_its_horizon(self):
        from tram.infrastructure.database import NetworkRow

        with self.sessions.begin() as session:
            row = session.get(NetworkRow, "demo-network-v1")
            document = copy.deepcopy(row.document)
            document["routes"][0]["route"]["valid_to"] = "2026-09-21"
            row.document = document
        with self.assertRaises(ApplicationError) as error:
            self.forecasts.create(self.command, "operator", "expired-route-key")
        self.assertEqual(error.exception.code, "UNSUPPORTED_PROFILE")

    def test_worker_and_map_share_saved_values(self):
        run, _ = self.forecasts.create(self.command, "operator", "test-key-1")
        with self.assertRaises(ApplicationError) as error:
            self.reads.points(run["id"], {"from": run["forecast_start"], "to": run["forecast_end"]})
        self.assertEqual(error.exception.code, "RESULT_NOT_READY")
        self.assertTrue(RunWorker(self.repo, self.clock, SeasonalNaive()).execute_one())
        completed = self.repo.run(run["id"])
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(completed["point_count"], 24)
        graph = self.reads.points(
            run["id"],
            {"from": "2026-09-21T08:00:00+03:00", "to": "2026-09-21T09:00:00+03:00", "limit": 200},
        )
        map_result = self.reads.map(
            run["id"], {"interval_start": "2026-09-21T08:00:00+03:00", "limit": 200}
        )
        self.assertEqual(graph["items"][0], map_result["features"][0]["properties"])

    def test_expired_worker_cannot_publish_or_extend_lease(self):
        run, _ = self.forecasts.create(self.command, "operator", "test-key-1")
        first = self.repo.claim(NOW, 30, 3)
        second = self.repo.claim(NOW + timedelta(seconds=31), 30, 3)
        self.assertNotEqual(first["lease_token"], second["lease_token"])
        self.assertFalse(
            self.repo.complete(run["id"], first["lease_token"], [], NOW + timedelta(seconds=32))
        )
        self.assertFalse(
            self.repo.heartbeat(run["id"], first["lease_token"], NOW + timedelta(seconds=32), 30)
        )
        self.assertEqual(self.repo.run(run["id"])["status"], "running")

    def test_failed_publication_rolls_back_points_and_status(self):
        run, _ = self.forecasts.create(self.command, "operator", "test-key-1")
        claim = self.repo.claim(NOW, 30, 3)
        point = {
            "spatial": {
                "level": "stop",
                "route_id": "demo-route-01",
                "direction_id": "demo-outbound",
                "stop_id": "demo-stop-01",
                "stop_sequence": 1,
                "segment_id": None,
            },
            "interval_start": "2026-09-21T00:00:00+03:00",
            "interval_end": "2026-09-21T01:00:00+03:00",
            "value": 12,
            "missing_reason": None,
            "value_kind": "forecast",
            "prediction_interval": None,
            "quality": {"status": "ok", "coverage_ratio": 1, "flags": []},
        }
        with self.assertRaises(IntegrityError):
            self.repo.complete(run["id"], claim["lease_token"], [point, copy.deepcopy(point)], NOW)
        self.assertEqual(self.repo.run(run["id"])["status"], "running")
        self.assertEqual(self.repo.forecast_points(run["id"], {}, 0, 10), [])

    def test_attempt_limit_terminates_abandoned_job(self):
        run, _ = self.forecasts.create(self.command, "operator", "test-key-1")
        self.repo.claim(NOW, 30, 1)
        self.assertIsNone(self.repo.claim(NOW + timedelta(seconds=31), 30, 1))
        self.assertEqual(self.repo.run(run["id"])["failure"]["code"], "ATTEMPTS_EXHAUSTED")

    def test_foreign_keys_are_active(self):
        with self.assertRaises(IntegrityError), self.sessions.begin() as session:
            session.add(
                ForecastPointRow(
                    run_id="missing",
                    **point_columns(
                        {
                            "spatial": {
                                "level": "route",
                                "route_id": "r",
                                "direction_id": None,
                                "stop_id": None,
                                "stop_sequence": None,
                                "segment_id": None,
                            },
                            "interval_start": "2026-09-21T00:00:00Z",
                            "interval_end": "2026-09-21T01:00:00Z",
                        }
                    ),
                )
            )

    def test_cursor_bound_to_filters_and_tamper_protected(self):
        query = {
            "dataset_revision_id": "demo-data-v1",
            "observation_profile_id": "demo-validations-stop-hour",
            "from": "2026-09-10T00:00:00+03:00",
            "to": "2026-09-11T00:00:00+03:00",
            "limit": 2,
        }
        first = self.reads.observations(query)
        cursor = first["page"]["next_cursor"]
        second = self.reads.observations({**query, "cursor": cursor})
        self.assertNotEqual(
            first["items"][0]["interval_start"], second["items"][0]["interval_start"]
        )
        for changed in ({**query, "limit": 3, "cursor": cursor}, {**query, "cursor": "x" + cursor}):
            with self.assertRaises(ApplicationError) as error:
                self.reads.observations(changed)
            self.assertEqual(error.exception.code, "INVALID_CURSOR")
