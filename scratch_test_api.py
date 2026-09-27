import urllib.request
import json

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/v1/auth/login',
    data=json.dumps({'username': 'admin', 'password': 'admin_password'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    with urllib.request.urlopen(req) as resp:
        print('Login status:', resp.status)
        data = json.loads(resp.read().decode('utf-8'))
        token = data.get('access_token', '')
        print('Token received:', token[:30], '...')
        
        # Test capabilities
        req2 = urllib.request.Request(
            'http://127.0.0.1:8000/api/v1/capabilities',
            headers={'Authorization': f'Bearer {token}'}
        )
        with urllib.request.urlopen(req2) as resp2:
            caps = json.loads(resp2.read().decode('utf-8'))
            print('Capabilities dataset_revision_id:', caps.get('dataset_revision_id'))
            print('Capabilities source_mode:', caps.get('source_mode'))
            print('Capabilities network_revision_id:', caps.get('network_revision_id'))

        # Test routes
        net_id = caps.get('network_revision_id')
        req3 = urllib.request.Request(
            f'http://127.0.0.1:8000/api/v1/routes?network_revision_id={net_id}&valid_at=2026-09-27&limit=1000',
            headers={'Authorization': f'Bearer {token}'}
        )
        with urllib.request.urlopen(req3) as resp3:
            routes = json.loads(resp3.read().decode('utf-8'))
            print('Routes count:', len(routes.get('items', [])))
            for r in routes.get('items', []):
                print('Route in DB:', r.get('route'))

except Exception as e:
    print('Error:', e)
