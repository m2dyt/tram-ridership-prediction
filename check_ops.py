import re

with open('openapi.yaml', 'r', errors='ignore') as f:
    yaml_text = f.read()

ops = re.findall(r'operationId:\s*([a-zA-Z0-9_]+)', yaml_text)

with open('backend/src/tram/api/app.py', 'r', encoding='utf-8') as f:
    app_text = f.read()

with open('backend/src/tram/api/extensions.py', 'r', encoding='utf-8') as f:
    ext_text = f.read()

missing = []
for op in ops:
    if f'"{op}"' not in app_text and f'"{op}"' not in ext_text and f"'{op}'" not in app_text and f"'{op}'" not in ext_text:
        # Also check composition.py for models
        with open('backend/src/tram/composition.py', 'r', encoding='utf-8') as f:
            comp_text = f.read()
        if f'"{op}"' not in comp_text and f"'{op}'" not in comp_text:
            missing.append(op)

print("Missing operations:", missing)
