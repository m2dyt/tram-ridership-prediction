# Тесты Python

Запускать `python -m pytest -q` из корня. Для PostgreSQL задать TRAM_TEST_DATABASE_URL и поднять отдельную test-db. [Инструкция](../docs/TESTING.md). Фикстуры синтетические; рабочие данные не очищаются.

## Файлы

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [browser_server.py](browser_server.py) | Изолированный UI smoke: временная SQLite, публичные тестовые ключи, демо, отчёты и worker без .env. |
| [support.py](support.py) | Общие доверенные синтетические фикстуры и фиксированные часы тестов. |
| [test_aggregation.py](test_aggregation.py) | Взвешивание по времени/вместимости, границы интервалов и публикация estimated-экспорта. |
| [test_api.py](test_api.py) | Контракт всех базовых HTTP-операций, авторизация, ошибки, строгий JSON и полный forecast pipeline. |
| [test_bootstrap.py](test_bootstrap.py) | Миграции up/down и metadata, направление зависимостей, согласованность Python-зависимостей. |
| [test_context.py](test_context.py) | Фикстуры провайдеров, редактирование секретов из ошибок, as_of-признаки и импорт GeoJSON. |
| [test_domain_ml.py](test_domain_ml.py) | Предметные интервалы/ключи, сезонная база, folds и граничные случаи метрик. |
| [test_evaluation_pipeline.py](test_evaluation_pipeline.py) | Публикация полных day/month/year отчётов и CSV-пропусков. |
| [test_fleet.py](test_fleet.py) | Округление выпуска, резерв, нулевой спрос и контракт сценарного API. |
| [test_occupancy.py](test_occupancy.py) | Три сценария, баланс, измеренные высадки, replay/конфликты и контракт API рейсов. |
| [test_postgres.py](test_postgres.py) | Реальная конкурентность PostgreSQL: публикация, идемпотентность, SKIP LOCKED, fencing и события рейса. |
| [test_publication.py](test_publication.py) | Атомарная публикация, повторы/ошибки/откат, demo и все горизонты. |
| [test_repository.py](test_repository.py) | SQL-проекции, очереди, фильтры, временная валидность сети и пагинация. |
