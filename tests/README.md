# Тесты Python

Запускать `python -m pytest -q` из корня. Для PostgreSQL задать TRAM_TEST_DATABASE_URL и поднять отдельную test-db. [Инструкция](../docs/TESTING.md). Фикстуры синтетические; рабочие данные не очищаются.

## Какие проверки выбирать

Изменение формул — соответствующие domain/ML тесты; новый импорт — publication/context и его граничные случаи; изменение API — контрактный сценарий; очередь и блокировки — реальная PostgreSQL. `test_bootstrap.py` защищает направление зависимостей и согласованность схемы. Эти тесты подтверждают поведение кода, но не измеряют точность на реальных пассажирах.

Для будущего обучения добавить проверки временного разбиения, доступности лагов/контекста, совпадения train/inference-признаков, сохранения/загрузки кандидата и раздельной оценки с baseline. Проверка качества на настоящих данных — отдельный воспроизводимый отчёт в эксперименте, не тест с заранее подогнанным порогом на синтетике.

## Файлы

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [browser_server.py](browser_server.py) | Изолированный UI smoke: временная SQLite, публичные тестовые ключи, демо, отчёты и worker без .env. |
| [support.py](support.py) | Общие доверенные синтетические фикстуры и фиксированные часы тестов. |
| [test_aggregation.py](test_aggregation.py) | Взвешивание по времени/вместимости, границы интервалов и публикация estimated-экспорта. |
| [test_api.py](test_api.py) | HTTP-контракт, роли регистрации, вход и `429`, прогнозный pipeline, безопасное чтение бандлов моделей. |
| [test_auth.py](test_auth.py) | Регистрация viewer/operator, вход, refresh и ограничение попыток через фейковые порты. |
| [test_bootstrap.py](test_bootstrap.py) | Миграции up/down и metadata, направление зависимостей, согласованность Python-зависимостей. |
| [test_context.py](test_context.py) | Фикстуры провайдеров, редактирование секретов из ошибок, as_of-признаки и импорт GeoJSON. |
| [test_domain_ml.py](test_domain_ml.py) | Предметные интервалы/ключи, сезонная база, folds и граничные случаи метрик. |
| [test_evaluation_pipeline.py](test_evaluation_pipeline.py) | Публикация полных day/month/year отчётов и CSV-пропусков. |
| [test_fleet.py](test_fleet.py) | Округление выпуска, резерв, нулевой спрос и контракт сценарного API. |
| [test_login_attempts.py](test_login_attempts.py) | Счётчик в SQLite: общий лимит, изоляция пары, истечение окна и очистка. |
| [test_metro_pipeline.py](test_metro_pipeline.py) | Метро: нули/пропуски, ID, сохранение потока, контроль файлов, временная база, покрытие и CLI без БД. |
| [test_ml_training.py](test_ml_training.py) | Проверка инженерии признаков без утечек и пайплайнов обучения/валидации моделей. |
| [test_model_selection.py](test_model_selection.py) | Выбор модели при создании запуска, исполнение worker ровно закреплённой модели, политика отказа бандла, `/health` и настоящий экспортированный baseline-бандл. |
| [test_occupancy.py](test_occupancy.py) | Три сценария, баланс, измеренные высадки, replay/конфликты и контракт API рейсов. |
| [test_postgres.py](test_postgres.py) | Реальная конкурентность PostgreSQL: публикация, идемпотентность, SKIP LOCKED, fencing и события рейса. |
| [test_publication.py](test_publication.py) | Атомарная публикация, повторы/ошибки/откат, demo и все горизонты. |
| [test_repository.py](test_repository.py) | SQL-проекции, очереди, фильтры, временная валидность сети и пагинация. |
| [test_artifact_predictor.py](test_artifact_predictor.py) | Инфраструктурный адаптер ArtifactPredictor: загрузка активного бандла, инференс и fallback на SeasonalNaive. |
| [test_benchmark.py](test_benchmark.py) | Проверка скрипта бенчмарка инференса, квантилей p50/p95/p99, RPS и генерации JSON отчёта. |
| [test_model_bundle.py](test_model_bundle.py) | Сериализация, валидация контрольных сумм SHA-256 и защита бандлов моделей от повреждения. |
| [test_submission_validation.py](test_submission_validation.py) | Строгая валидация конкурсных сабмитов (14640 строк, 10 маршрутов, нулевой маршрут 5). |
| [test_tram_training_modules.py](test_tram_training_modules.py) | Модули обучения трамвая: сетка, профили, метрика WAPE-score, CatBoost/HistGradientBoosting модели. |
| [test_weather_and_calendar.py](test_weather_and_calendar.py) | Пайплайны внешних данных: погода 2025 (Open-Meteo) и официальный календарь РФ 2025. |
| [test_tram_data.py](test_tram_data.py) | Проверка схем данных, семантики нуля/пропусков, первичных ключей, временных сплитов и манифеста. |
| [test_forecast_rollup.py](test_forecast_rollup.py) | Агрегация прогноза: суммы и пики, пропуски не как ноль, среднее для неаддитивных показателей, календарные и пространственные группы, запрет неподдерживаемых группировок. |
| [test_allocation.py](test_allocation.py) | Распределение итога маршрута по остановкам: сохранение суммы, вес пересадочных узлов, маршрут без остановок. |
| [test_shared_operator.py](test_shared_operator.py) | Общий оператор: хеш соответствует паролю из docs/DOCKER_STACK.md, учётная запись создаётся и восстанавливается. |
| [test_forecast_load.py](test_forecast_load.py) | Наполненность по прогнозу: баланс пассажиров, конечная, пропуски прогноза, соответствие контракту на демо-данных. |
