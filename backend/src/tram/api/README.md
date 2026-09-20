# HTTP API

Исполняемый контракт — [openapi.yaml](../../../../openapi.yaml), Swagger — `/docs`, базовый путь — `/api/v1`. GET требует viewer/operator, POST — operator, `/health` публичный. Новая операция добавляется одновременно в контракт, binding и тест ответа.

## Файлы

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [app.py](app.py) | HTTP-адаптер: Bearer-роли, строгий JSON, JSON Schema, параметры, ошибки, CORS и маршруты из OpenAPI. |
| [extensions.py](extensions.py) | Привязка операций рейсов, контекста и калькулятора к сервисам и чистым функциям. |
