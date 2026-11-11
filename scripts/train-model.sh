#!/bin/sh
set -eu

# The version name depends on the labels and on the service recipe, so new data or a new
# recipe always gives a new bundle and never overwrites the served one.
version="$(python - <<'PY'
import hashlib
from pathlib import Path

from ml.training.tram.adaptive import RECIPE

digest = hashlib.sha256(RECIPE.encode())
for name in ("labels_day_train.csv", "labels_day_test.csv"):
    path = Path("/app/dataset/labels") / name
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
print("service-" + digest.hexdigest()[:12])
PY
)"
models_root=/app/models/tram

if [ ! -f "$models_root/$version/manifest.json" ]; then
  # Holdout check of the last 8 weeks, model choice, intervals, then a refit on all history.
  python -m ml.training.tram.service \
    --data-dir /app/dataset \
    --models-root "$models_root" \
    --version "$version" \
    --set-active
  # Honest day-by-day check of the version fitted before the holdout; shown on «Качество».
  python scripts/evaluate_check_model.py "$version-check"
else
  python - "$version" <<'PY'
import sys
from pathlib import Path
from ml.training.tram.bundle import set_active_version

set_active_version(sys.argv[1], models_root=Path("/app/models/tram"))
PY
fi

printf 'Active ML bundle: %s\n' "$version"
