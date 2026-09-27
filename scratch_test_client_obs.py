from tram.composition import create_app
from starlette.testclient import TestClient
import json

app = create_app()
client = TestClient(app)

# Login
login_res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin_password"})
token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Test getObservations
params = {
    "dataset_revision_id": "competition-data-v1",
    "observation_profile_id": "competition-boardings-route-day",
    "route_id": "hackathon-1",
    "from": "2025-01-01T00:00:00+03:00",
    "to": "2025-01-10T00:00:00+03:00"
}
resp = client.get("/api/v1/observations", params=params, headers=headers)
print("Status:", resp.status_code)
data = resp.json()
print("Items count:", len(data.get("items", [])))
if not data.get("items"):
    print("Full response:", data)
else:
    print("First item:", data["items"][0])
