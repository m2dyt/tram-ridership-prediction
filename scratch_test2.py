import sys
import json
import urllib.parse
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path("backend/src").absolute()))
from tram.composition import create_app

app = create_app()
client = TestClient(app)
headers = {"Authorization": "Bearer viewer-secret-token-viewer-secret-token"}
op_headers = {"Authorization": "Bearer operator-secret-token-operator-secret-token", "Idempotency-Key": "test-key-1"}

res = client.get('/api/v1/capabilities?dataset_revision_id=demo-data-v3-20260927', headers=headers)
prof = res.json()['forecast_profiles'][0]
as_of = prof['allowed_as_of_start']
f_start = prof['forecast_start_min']

payload = {
    "dataset_revision_id": "demo-data-v3-20260927",
    "profile_id": prof['id'],
    "route_ids": ["demo-route-01"],
    "as_of": as_of,
    "forecast_start": f_start
}
res = client.post('/api/v1/forecast-runs', json=payload, headers=op_headers)
run_id = res.json()['id']

as_of_enc = urllib.parse.quote(as_of)
f_start_enc = urllib.parse.quote(f_start)

res_pts = client.get(f'/api/v1/forecast-runs/{run_id}/points?from={as_of_enc}&to={f_start_enc}', headers=headers)
print('Points Body:', res_pts.json())

