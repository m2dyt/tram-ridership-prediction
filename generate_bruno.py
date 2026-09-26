import os

os.makedirs("bruno", exist_ok=True)

tests = [
    ("01-health", "get", "/health", ""),
    ("02-register", "post", "/auth/register", '{"username": "newuser", "password": "newpassword"}'),
    ("03-login", "post", "/auth/login", '{"username": "newuser", "password": "newpassword"}', "bru.setEnvVar('token', res.body.access_token);"),
    ("04-me", "get", "/auth/me", ""),
    ("05-refresh", "post", "/auth/refresh", ""),
    ("06-capabilities", "get", "/capabilities", ""),
    ("07-data-status", "get", "/data-status", ""),
    ("08-network", "get", "/network?network_revision_id=demo-network-v3", ""),
    ("09-routes", "get", "/routes?network_revision_id=demo-network-v3&valid_at=2026-09-20", ""),
    ("10-route", "get", "/routes/demo-route-01?network_revision_id=demo-network-v3&valid_at=2026-09-20", ""),
    ("11-stops", "get", "/stops?network_revision_id=demo-network-v3&valid_at=2026-09-20", ""),
    ("12-observations", "get", "/observations?dataset_revision_id=demo-data-v1&observation_profile_id=demo-validations-route-hour&from=2026-09-19T08:00:00%2B03:00&to=2026-09-19T09:00:00%2B03:00", ""),
    ("13-create-forecast", "post", "/forecast-runs", '{\n  "dataset_revision_id": "demo-data-v1",\n  "network_revision_id": "demo-network-v3",\n  "profile_id": "demo-validations-day",\n  "route_ids": ["demo-route-01"],\n  "as_of": "2026-09-20T18:00:00+03:00",\n  "forecast_start": "2026-09-21T00:00:00+03:00"\n}', "bru.setEnvVar('run_id', res.body.id);"),
    ("14-list-forecasts", "get", "/forecast-runs", ""),
    ("15-get-forecast", "get", "/forecast-runs/{{run_id}}", ""),
    ("16-forecast-points", "get", "/forecast-runs/{{run_id}}/points?metric=validations", ""),
    ("17-forecast-map", "get", "/forecast-runs/{{run_id}}/map?metric=validations", ""),
    ("18-list-evaluations", "get", "/evaluations", ""),
    ("19-get-evaluation", "get", "/evaluations/demo-validations-day", ""),
    ("20-evaluation-points", "get", "/evaluations/demo-validations-day/points?metric=validations", ""),
    ("21-logout", "post", "/auth/logout", "")
]

for name, method, path, body, *script in tests:
    filename = f"bruno/{name}.bru"
    content = f"""meta {{
  name: {name}
  type: http
  seq: {name.split('-')[0]}
}}

{method} {{
  url: http://localhost:8002/api/v1{path}
  body: {"json" if method == "post" and body else "none"}
  auth: {"none" if name in ["01-health", "02-register", "03-login"] else "bearer"}
}}

"""
    if name not in ["01-health", "02-register", "03-login"]:
        content += """auth:bearer {
  token: {{token}}
}

"""
    if name == "13-create-forecast":
        content += """headers {
  Idempotency-Key: run-demo-1
}

"""
    if body:
        content += f"""body:json {{
  {body}
}}

"""
    if script:
        content += f"""script:post-response {{
  if(res.status == 200) {{
    {script[0]}
  }}
}}
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

print("Generated all bruno tests!")
