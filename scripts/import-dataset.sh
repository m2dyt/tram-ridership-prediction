#!/bin/sh
set -eu

python /app/scripts/build_competition_bundle.py \
  --data-dir /app/dataset \
  --output-dir /tmp/competition-bundle \
  --project-root /app
python -m tram.cli publish /tmp/competition-bundle
