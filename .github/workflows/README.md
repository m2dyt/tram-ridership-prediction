# Workflow

CI использует отдельную PostgreSQL-службу и выполняет backend/frontend проверки на push и pull_request.

## Файлы

| Файл | Назначение |
|---|---|
| [checks.yml](checks.yml) | CI: PostgreSQL, Python 3.12, pip/pytest/Ruff, Node, npm ci, тесты/сборка/Prettier. |
