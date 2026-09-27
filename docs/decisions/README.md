# Архитектурные решения

ADR сохраняют выбранные границы и стек. При изменении решения добавлять новую запись с причиной, не переписывая историю без отметки.

## Файлы

| Файл | Назначение |
|---|---|
| [0001-clean-architecture.md](0001-clean-architecture.md) | ADR: слои и направление зависимостей backend/ML. |
| [0002-frontend-stack.md](0002-frontend-stack.md) | ADR: React на JavaScript, Vite, OSM/Leaflet. |
| [0003-auth-roles-and-static-tokens.md](0003-auth-roles-and-static-tokens.md) | ADR: регистрация выдаёт только viewer, operator создаётся отдельным защищённым эндпоинтом, статические токены сосуществуют с JWT. |
