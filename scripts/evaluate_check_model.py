"""Publish a quality report for the check version of the service model.

    python scripts/evaluate_check_model.py <version>-check

The check version was fitted only on history before its holdout weeks, so every day of the
holdout is an honest out-of-sample test. One fold is made per day (a day-ahead forecast, as
the service makes it), and the report shows the model next to the seasonal baseline on the
latest published dataset. It appears on the «Качество» screen.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Run as a file (python scripts/evaluate_check_model.py): the repository root holds the ml
# package that the model bundle needs, so put it on the import path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tram.cli import main as tram_main  # noqa: E402
from tram.infrastructure.database import make_engine, session_factory  # noqa: E402
from tram.infrastructure.repository import SqlRepository  # noqa: E402
from tram.infrastructure.settings import Settings  # noqa: E402


def main(version: str) -> int:
    settings = Settings()
    config = json.loads((Path(settings.models_root) / version / "config.json").read_text())
    start = datetime.fromisoformat(config["training_history_end"])
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        dataset = SqlRepository(session_factory(engine)).dataset(None)
    finally:
        engine.dispose()
    if dataset is None:
        print("No published dataset; publish data before the check", file=sys.stderr)
        return 1
    caps = dataset["capabilities"]
    profile = next(
        p
        for p in caps["forecast_profiles"]
        if p["horizon"] == "day" and p["resolution"] == "hour" and p["spatial_level"] == "route"
    )
    observed = next(
        p for p in caps["observation_profiles"] if p["id"] == profile["observation_profile_id"]
    )
    end = datetime.fromisoformat(observed["history_end"])
    origins = []
    day = start
    while day + timedelta(days=1) <= end and len(origins) < 100:
        origins.append(day.isoformat())
        day += timedelta(days=1)
    arguments = ["evaluate", "--dataset", caps["dataset_revision_id"], "--profile", profile["id"]]
    arguments += ["--model-version", version]
    for origin in origins:
        arguments += ["--origin", origin]
    return tram_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
