import re
with open('openapi.yaml', 'r', encoding='utf-8') as f:
    text = f.read()

pattern = r"(?s)(/network:.*?200:\s*description:[^\n]*\n\s*content:\s*application/json:\s*schema:\s*)type: object\s*additionalProperties: true"
replacement = r"\1$ref: '#/components/schemas/NetworkPage'"

text = re.sub(pattern, replacement, text, count=1)
with open('openapi.yaml', 'w', encoding='utf-8') as f:
    f.write(text)
