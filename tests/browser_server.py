"""Disposable local UI smoke server. Own SQLite file and public test-only tokens; no .env."""

import tempfile
import threading
from pathlib import Path

import uvicorn
from tram.api.app import create_http_app
from tram.api.extensions import context_bindings, occupancy_bindings
from tram.application.context import ContextService
from tram.application.occupancy import OccupancyService
from tram.application.publication import PublishDataset
from tram.application.service import ForecastService, ReadService
from tram.application.worker import RunWorker
from tram.infrastructure.bundles import read_bundle
from tram.infrastructure.context_store import SqlSnapshotStore
from tram.infrastructure.contract import Contract
from tram.infrastructure.database import Base, make_engine, session_factory
from tram.infrastructure.demo import write_demo
from tram.infrastructure.publication import SqlDatasetWriter
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SignedCursor, SystemClock
from tram.infrastructure.sources import ExternalSources
from tram.infrastructure.trips import SqlTripStore
from tram_ml.baseline import SeasonalNaive


def main():
    with tempfile.TemporaryDirectory(prefix="tram-browser-") as directory:
        root = Path(directory)
        clock, contract = SystemClock(), Contract(Path("openapi.yaml"))
        write_demo(root / "demo", clock.now())
        engine = make_engine("sqlite+pysqlite:///" + (root / "smoke.db").as_posix())
        Base.metadata.create_all(engine)
        sessions = session_factory(engine)
        manifest, records = read_bundle(root / "demo", contract)
        PublishDataset(SqlDatasetWriter(sessions), clock).execute(manifest, records)
        repo = SqlRepository(sessions)
        reads = ReadService(repo, clock, SignedCursor("browser-test-cursor-" * 3))
        trip_service = OccupancyService(SqlTripStore(sessions), clock, reads)
        from tram.infrastructure.contract import strict_json

        plan = strict_json((root / "demo/trip-plan.json").read_bytes())
        trip_service.create(plan)
        for line in (root / "demo/trip-events.jsonl").read_text().splitlines():
            trip_service.apply(plan["trip_id"], strict_json(line))
        from tram.application.evaluation import EvaluateBaseline
        from tram.infrastructure.evaluation import SqlEvaluationStore
        from tram_ml.evaluation import score, temporal_folds

        runner = EvaluateBaseline(
            repo,
            SqlEvaluationStore(sessions, contract),
            reads,
            clock,
            SeasonalNaive(),
            temporal_folds,
            score,
        )
        for horizon, origin in strict_json(
            (root / "demo/evaluation-origins.json").read_bytes()
        ).items():
            runner.execute(
                manifest["capabilities"]["dataset_revision_id"],
                "demo-validations-" + horizon,
                [origin],
            )
        extra_reads, extra_commands = occupancy_bindings(trip_service)
        cr, cc = context_bindings(
            ContextService(SqlSnapshotStore(sessions), ExternalSources(), clock, reads)
        )
        extra_reads.update(cr)
        extra_commands.update(cc)
        app = create_http_app(
            reads,
            ForecastService(repo, clock, reads),
            contract,
            viewer_token="browser-viewer-" * 3,
            operator_token="browser-operator-" * 3,
            extra_reads=extra_reads,
            extra_commands=extra_commands,
        )
        stop = threading.Event()
        worker = RunWorker(repo, clock, SeasonalNaive())

        def loop():
            while not stop.wait(0.3):
                worker.execute_one()

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        try:
            uvicorn.run(app, host="127.0.0.1", port=8002)
        finally:
            stop.set()
            thread.join(timeout=5)
            engine.dispose()


if __name__ == "__main__":
    main()
