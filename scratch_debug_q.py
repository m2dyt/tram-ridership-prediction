from tram.composition import create_app
from starlette.testclient import TestClient

app = create_app()
client = TestClient(app)

login_res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin_password"})
token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

params = {
    "dataset_revision_id": "competition-data-v1",
    "observation_profile_id": "competition-boardings-route-day",
    "route_id": "hackathon-1",
    "from": "2025-01-01T00:00:00+03:00",
    "to": "2025-01-10T00:00:00+03:00"
}

# Monkey patch reads.observations to print q
reads = app.state.reads
original_obs = reads.observations
def debug_obs(q):
    print("DEBUG_OBS q passed to reads.observations:", q)
    res = original_obs(q)
    print("DEBUG_OBS items len:", len(res.get("items", [])))
    return res
reads.observations = debug_obs

resp = client.get("/api/v1/observations", params=params, headers=headers)
