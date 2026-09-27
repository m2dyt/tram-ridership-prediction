import urllib.request
import json

req = urllib.request.Request("http://127.0.0.1:8000/api/v1/capabilities")
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        print("Status:", resp.status)
        print("Dataset revision:", data.get("dataset_revision_id"))
        print("Network revision:", data.get("network_revision_id"))
        print("Source mode:", data.get("source_mode"))
        print("Forecast profiles count:", len(data.get("forecast_profiles", [])))
        print("Observation profiles count:", len(data.get("observation_profiles", [])))
        if data.get("forecast_profiles"):
            print("First forecast profile:", json.dumps(data["forecast_profiles"][0], indent=2, ensure_ascii=False))
        if data.get("observation_profiles"):
            print("First observation profile:", json.dumps(data["observation_profiles"][0], indent=2, ensure_ascii=False))
except Exception as e:
    print("Error calling /capabilities:", e)
