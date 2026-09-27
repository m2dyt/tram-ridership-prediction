#!/bin/sh
set -eu

version="$(python - <<'PY'
import hashlib
from pathlib import Path

digest = hashlib.sha256()
for name in ("labels_day_train.csv", "labels_day_test.csv"):
    path = Path("/app/dataset/labels") / name
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
print("competition-2025-" + digest.hexdigest()[:12])
PY
)"
models_root=/app/models/tram

if [ ! -f "$models_root/$version/manifest.json" ]; then
  python -m ml.training.tram.cli \
    --data-dir /app/dataset \
    --output-dir /app/ml/predictions \
    --cpu \
    --model histgradient \
    --no-per-route \
    --iterations 160 \
    --learning-rate 0.05 \
    --depth 6 \
    --no-weather \
    --no-route-features \
    --eval-only \
    --export-bundle "$version" \
    --set-active
else
  python - "$version" <<'PY'
import sys
from pathlib import Path
from ml.training.tram.bundle import set_active_version

set_active_version(sys.argv[1], models_root=Path("/app/models/tram"))
PY
fi

printf 'Active ML bundle: %s\n' "$version"
