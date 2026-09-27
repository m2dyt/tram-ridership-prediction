import urllib.request, json, urllib.parse

req = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login', data=json.dumps({'username': 'admin', 'password': 'admin_password'}).encode('utf-8'), headers={'Content-Type': 'application/json'})
token = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))['access_token']

# Check without route_id first
params = {
    'dataset_revision_id': 'competition-data-v1',
    'observation_profile_id': 'competition-boardings-route-day',
    'from': '2025-01-01T00:00:00+03:00',
    'to': '2025-01-10T00:00:00+03:00',
}
qs = urllib.parse.urlencode(params)
req2 = urllib.request.Request(f'http://127.0.0.1:8000/api/v1/observations?{qs}', headers={'Authorization': f'Bearer {token}'})
try:
    resp = urllib.request.urlopen(req2)
    data = json.loads(resp.read().decode('utf-8'))
    print("Without route_id - Items count:", len(data.get("items", [])))
except urllib.error.HTTPError as e:
    print("Without route_id - HTTP error:", e.code, e.read().decode('utf-8'))

# Check with route_id=hackathon-1
params['route_id'] = 'hackathon-1'
qs = urllib.parse.urlencode(params)
req3 = urllib.request.Request(f'http://127.0.0.1:8000/api/v1/observations?{qs}', headers={'Authorization': f'Bearer {token}'})
try:
    resp = urllib.request.urlopen(req3)
    data = json.loads(resp.read().decode('utf-8'))
    print("With route_id=hackathon-1 - Items count:", len(data.get("items", [])))
    if data.get("items"):
        print("Sample item:", data["items"][0])
except urllib.error.HTTPError as e:
    print("With route_id - HTTP error:", e.code, e.read().decode('utf-8'))
