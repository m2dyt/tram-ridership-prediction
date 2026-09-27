import urllib.request, json, urllib.parse

req = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login', data=json.dumps({'username': 'admin', 'password': 'admin_password'}).encode('utf-8'), headers={'Content-Type': 'application/json'})
token = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))['access_token']

params = {
    'dataset_revision_id': 'competition-data-v1',
    'observation_profile_id': 'competition-boardings-route-day',
    'from': '2025-01-01T00:00:00+03:00',
    'to': '2025-01-02T00:00:00+03:00',
}
qs = urllib.parse.urlencode(params)
req2 = urllib.request.Request(f'http://127.0.0.1:8000/api/v1/observations?{qs}', headers={'Authorization': f'Bearer {token}'})
resp = urllib.request.urlopen(req2)
data = json.loads(resp.read().decode('utf-8'))
for item in data.get('items', []):
    print("Item spatial:", item.get("spatial"), "Value:", item.get("value"))
