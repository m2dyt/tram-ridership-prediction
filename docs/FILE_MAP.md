# Полная карта файлов

Поддерживаемые файлы проекта. Временные данные, секреты, зависимости и результаты сборки исключены из Git. Для sources/data/models отслеживаются только README. Назначение файлов, входы/выходы и следующие действия находятся в README соответствующих папок. Путь до обучения — [TRAINING_PLAN.md](TRAINING_PLAN.md).

## .

| Файл | Назначение |
|---|---|
| [.dockerignore](../.dockerignore) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [.env.example](../.env.example) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [.gitattributes](../.gitattributes) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [.gitignore](../.gitignore) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [.python-version](../.python-version) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [alembic.ini](../alembic.ini) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [compose.yaml](../compose.yaml) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [Dockerfile](../Dockerfile) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [openapi.yaml](../openapi.yaml) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [pyproject.toml](../pyproject.toml) | Конфигурация/точка входа проекта; подробно описана в корневом README. |
| [README.md](../README.md) | Навигация и инструкция компонента. |
| [requirements.txt](../requirements.txt) | Конфигурация/точка входа проекта; подробно описана в корневом README. |

## .github

| Файл | Назначение |
|---|---|
| [README.md](../.github/README.md) | Навигация и инструкция компонента. |

## .github/workflows

| Файл | Назначение |
|---|---|
| [checks.yml](../.github/workflows/checks.yml) | CI: PostgreSQL, Python 3.12, pip/pytest/Ruff, Node, npm ci, тесты/сборка/Prettier. |
| [README.md](../.github/workflows/README.md) | Навигация и инструкция компонента. |

## backend

| Файл | Назначение |
|---|---|
| [README.md](../backend/README.md) | Навигация и инструкция компонента. |

## backend/migrations

| Файл | Назначение |
|---|---|
| [env.py](../backend/migrations/env.py) | Окружение Alembic: metadata приложения, секретный URL из настроек, online/offline миграции. |
| [README.md](../backend/migrations/README.md) | Навигация и инструкция компонента. |
| [script.py.mako](../backend/migrations/script.py.mako) | Шаблон новой миграции; не исполняется при обычном запуске. |

## backend/migrations/versions

| Файл | Назначение |
|---|---|
| [0001_initial.py](../backend/migrations/versions/0001_initial.py) | Начальная схема версий, наблюдений, очереди, прогнозных точек и отчётов оценки. |
| [0002_run_status_times.py](../backend/migrations/versions/0002_run_status_times.py) | Время переходов состояния очереди для стабильной пагинации. |
| [0003_persist_trip_balance_and_context_.py](../backend/migrations/versions/0003_persist_trip_balance_and_context_.py) | Таблицы рейсов, событий/checkpoints и внешних снимков; ограничения и индексы. |
| [README.md](../backend/migrations/versions/README.md) | Навигация и инструкция компонента. |

## backend/src

| Файл | Назначение |
|---|---|
| [README.md](../backend/src/README.md) | Навигация и инструкция компонента. |

## backend/src/tram

| Файл | Назначение |
|---|---|
| [__init__.py](../backend/src/tram/__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [cli.py](../backend/src/tram/cli.py) | Основные команды: диагностика, конфигурация, demo/publish, миграции, API и worker; делегирование дополнительных команд. |
| [commands.py](../backend/src/tram/commands.py) | CLI для снимков, GeoJSON, CSV, replay, backtesting и экспорта наполненности; соединяет адаптеры со сценариями. |
| [composition.py](../backend/src/tram/composition.py) | Точка сборки приложения: настройки, SQL, часы, порты, HTTP, ML и раздача frontend/dist. |
| [README.md](../backend/src/tram/README.md) | Навигация и инструкция компонента. |

## backend/src/tram/api

| Файл | Назначение |
|---|---|
| [__init__.py](../backend/src/tram/api/__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [app.py](../backend/src/tram/api/app.py) | HTTP-адаптер: Bearer-роли, строгий JSON, JSON Schema, параметры, ошибки, CORS и маршруты из OpenAPI. |
| [extensions.py](../backend/src/tram/api/extensions.py) | Привязка операций рейсов, контекста и калькулятора к сервисам и чистым функциям. |
| [README.md](../backend/src/tram/api/README.md) | Навигация и инструкция компонента. |

## backend/src/tram/application

| Файл | Назначение |
|---|---|
| [__init__.py](../backend/src/tram/application/__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [context.py](../backend/src/tram/application/context.py) | Порты источника/снимков и сценарий сохранения полученного контекста с available_at. |
| [errors.py](../backend/src/tram/application/errors.py) | Ошибки сценариев с кодами для HTTP/CLI. |
| [evaluation.py](../backend/src/tram/application/evaluation.py) | Оркестрация полных временных folds, прогноз/факт, срезы метрик и публикация отчёта через порты. |
| [mapping.py](../backend/src/tram/application/mapping.py) | Преобразование JSON пространственных ключей в domain-типы и обратно. |
| [occupancy.py](../backend/src/tram/application/occupancy.py) | Сценарии создания/чтения рейса, проверки сети и доступности события, идемпотентные fingerprint. |
| [occupancy_export.py](../backend/src/tram/application/occupancy_export.py) | Построение проездов по участкам из журналов и prepared bundle восстановленной наполненности. |
| [ports.py](../backend/src/tram/application/ports.py) | Протоколы repository, clock, cursor, predictor и документы границ. |
| [publication.py](../backend/src/tram/application/publication.py) | Семантическая проверка сети, профилей, моделей, временной сетки и полного потока наблюдений. |
| [README.md](../backend/src/tram/application/README.md) | Навигация и инструкция компонента. |
| [service.py](../backend/src/tram/application/service.py) | Чтение каталогов/истории/результатов/оценок, фильтры и курсоры; создание прогнозных запусков. |
| [worker.py](../backend/src/tram/application/worker.py) | Получение задания с lease, чтение разрешённой истории, вызов предиктора и атомарная публикация результата. |

## backend/src/tram/domain

| Файл | Назначение |
|---|---|
| [__init__.py](../backend/src/tram/domain/__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [aggregation.py](../backend/src/tram/domain/aggregation.py) | Среднее по длительности проездов, отдельная нормализация на вместимость каждого вагона. |
| [errors.py](../backend/src/tram/domain/errors.py) | Предметная ошибка нарушения инварианта. |
| [fleet.py](../backend/src/tram/domain/fleet.py) | Сценарный расчёт числа вагонов, интервала движения и дефицита резерва без оптимизации. |
| [occupancy.py](../backend/src/tram/domain/occupancy.py) | Распределение групп по остановкам, баланс массы, измеренные высадки, конечная и переполнение. |
| [README.md](../backend/src/tram/domain/README.md) | Навигация и инструкция компонента. |
| [series.py](../backend/src/tram/domain/series.py) | Показатели, пространственные ключи, наблюдения и прогнозные точки; проверки значений. |
| [time.py](../backend/src/tram/domain/time.py) | UTC/Moscow, RFC3339, интервалы, календарные горизонты и допустимые временные сетки. |

## backend/src/tram/infrastructure

| Файл | Назначение |
|---|---|
| [__init__.py](../backend/src/tram/infrastructure/__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [bundles.py](../backend/src/tram/infrastructure/bundles.py) | Чтение и структурная проверка manifest.json и последовательного observations.jsonl. |
| [context_store.py](../backend/src/tram/infrastructure/context_store.py) | Запись и чтение неизменяемых снимков, фильтры provider/kind и пагинация. |
| [contract.py](../backend/src/tram/infrastructure/contract.py) | Загрузка OpenAPI, JSON Schema, строгий JSON без дубликатов ключей и нечисловых NaN. |
| [csv_import.py](../backend/src/tram/infrastructure/csv_import.py) | Потоковое преобразование точного CSV-формата агрегатов в prepared bundle. |
| [database.py](../backend/src/tram/infrastructure/database.py) | SQLAlchemy-модели, UTC timestamp, engine/session factory и ограничения таблиц. |
| [demo.py](../backend/src/tram/infrastructure/demo.py) | Синтетические данные текущей даты, сеть из четырёх остановок, запросы, план/журнал рейса и отсечки оценки. |
| [evaluation.py](../backend/src/tram/infrastructure/evaluation.py) | Выборка фактов и транзакционная публикация проверенных по контракту отчёта и точек оценки. |
| [geo_import.py](../backend/src/tram/infrastructure/geo_import.py) | Импорт WGS84 Point GeoJSON Москвы с явными полями, проверками координат/ID и SHA-256. |
| [publication.py](../backend/src/tram/infrastructure/publication.py) | SQL-публикация набора одной транзакцией, хеширование потока, пакетные вставки и блокировки повторов. |
| [README.md](../backend/src/tram/infrastructure/README.md) | Навигация и инструкция компонента. |
| [repository.py](../backend/src/tram/infrastructure/repository.py) | SQL-чтение версий/точек/отчётов, очередь, идемпотентность запросов, lease/fencing и публикация прогнозов. |
| [runtime.py](../backend/src/tram/infrastructure/runtime.py) | Системные часы и подписанные HMAC курсоры пагинации. |
| [settings.py](../backend/src/tram/infrastructure/settings.py) | Типизированные TRAM_* настройки из .env/окружения; SecretStr и проверка ключей. |
| [sources.py](../backend/src/tram/infrastructure/sources.py) | Ограниченные HTTP-клиенты Open-Meteo, WeatherAPI, KudaGo, Timepad и нормализация ответов без утечки ключей. |
| [trips.py](../backend/src/tram/infrastructure/trips.py) | Постоянное состояние рейсов и журнал checkpoints, PostgreSQL-блокировки по trip_id. |

## docs

| Файл | Назначение |
|---|---|
| [ARCHITECTURE.md](../docs/ARCHITECTURE.md) | Границы слоёв, поток данных, версии/время, очередь, баланс пассажиров и расширение. |
| [DATA_FORMAT.md](../docs/DATA_FORMAT.md) | Контракт prepared bundle: manifest, ряд, временная сетка, JSONL и происхождение. |
| [DATA_SOURCES.md](../docs/DATA_SOURCES.md) | Выбор внешних источников, официальные ссылки, условия доступности и ограничения. |
| [DATASETS.md](../docs/DATASETS.md) | Наборы 624/62743 пользователя, дополнительные источники, порядок получения, образцы и пробелы данных. |
| [DATA_AUDIT.md](../docs/DATA_AUDIT.md) | Аудит полученных архивов 624/62743: поля, покрытие, дубли, нули, координаты и ограничения соединения. |
| [DATA_LINK_CHECKS.json](../docs/DATA_LINK_CHECKS.json) | Фактические результаты проверки URL, время, ограничения и SHA-256 скачанных образцов. |
| [DELIVERY_PLAN.md](../docs/DELIVERY_PLAN.md) | План текущей реализации без обучения, порядок шагов и критерии проверки. |
| [FILE_MAP.md](../docs/FILE_MAP.md) | Полная карта поддерживаемых файлов и ссылок на папки. |
| [IMPLEMENTATION_LOG.md](../docs/IMPLEMENTATION_LOG.md) | История выполненных шагов: план → реализация → проверки → ревью. |
| [LOCAL_SETUP.md](../docs/LOCAL_SETUP.md) | Подробности Python/venv и диагностики локального окружения. |
| [OPERATIONS.md](../docs/OPERATIONS.md) | Готовые команды демо, оценки, источников, GeoJSON/CSV, replay, экспорта и калькулятора. |
| [PASSENGER_OCCUPANCY.md](../docs/PASSENGER_OCCUPANCY.md) | Математическая постановка восстановления высадок и остатка, сценарии и критерии валидации. |
| [README.md](../docs/README.md) | Навигация и инструкция компонента. |
| [STATUS.md](../docs/STATUS.md) | Сопоставление требований ТЗ с кодом и явные ограничения данных, источников и эксплуатации. |
| [TESTING.md](../docs/TESTING.md) | Полный запуск тестов без skip, frontend и временный browser smoke. |
| [TRAINING_PLAN.md](../docs/TRAINING_PLAN.md) | Пошаговая подготовка к обучению: постановка, данные, splits, признаки, кандидат, оценка, подключение. |

## docs/decisions

| Файл | Назначение |
|---|---|
| [0001-clean-architecture.md](../docs/decisions/0001-clean-architecture.md) | ADR: слои и направление зависимостей backend/ML. |
| [0002-frontend-stack.md](../docs/decisions/0002-frontend-stack.md) | ADR: React на JavaScript, Vite, OSM/Leaflet. |
| [README.md](../docs/decisions/README.md) | Навигация и инструкция компонента. |

## frontend

| Файл | Назначение |
|---|---|
| [index.html](../frontend/index.html) | HTML-точка входа приложения, язык, viewport, заголовок. |
| [package-lock.json](../frontend/package-lock.json) | Точные транзитивные npm-зависимости и integrity для воспроизводимого npm ci. |
| [package.json](../frontend/package.json) | Точные версии React/Leaflet/Vite/Prettier и команды разработки, сборки, тестов, форматирования. |
| [README.md](../frontend/README.md) | Навигация и инструкция компонента. |
| [vite.config.js](../frontend/vite.config.js) | Vite dev/proxy API+Swagger, порты, сборка и preview. |

## frontend/src

| Файл | Назначение |
|---|---|
| [App.jsx](../frontend/src/App.jsx) | Вход с ключом в памяти, навигация, версия набора/сети, выбор маршрута и переключение экранов. |
| [main.jsx](../frontend/src/main.jsx) | Монтирование React StrictMode и подключение стилей приложения/Leaflet. |
| [README.md](../frontend/src/README.md) | Навигация и инструкция компонента. |
| [styles.css](../frontend/src/styles.css) | Система цветов/типографики, сетки, карта, таблицы и адаптивная верстка. |

## frontend/src/api

| Файл | Назначение |
|---|---|
| [client.js](../frontend/src/api/client.js) | Fetch-клиент, Bearer, отмена, API-ошибки, сохранение фильтров и полная пагинация items/features. |
| [README.md](../frontend/src/api/README.md) | Навигация и инструкция компонента. |

## frontend/src/components

| Файл | Назначение |
|---|---|
| [Chart.jsx](../frontend/src/components/Chart.jsx) | SVG-график, выбор интервала карты и доступная таблица значений. |
| [Common.jsx](../frontend/src/components/Common.jsx) | Отменяемая загрузка ресурсов, состояния ошибки/пустоты, Badge, CSV-загрузка и безопасные внешние ссылки. |
| [Map.jsx](../frontend/src/components/Map.jsx) | Жизненный цикл Leaflet, OSM с атрибуцией, геометрии/попапы без HTML-инъекций и слои контекста. |
| [README.md](../frontend/src/components/README.md) | Навигация и инструкция компонента. |

## frontend/src/domain

| Файл | Назначение |
|---|---|
| [format.js](../frontend/src/domain/format.js) | Формат времени/чисел, подписи, идентичность ряда, CSV-экранирование и разрывы линии на пропусках. |
| [README.md](../frontend/src/domain/README.md) | Навигация и инструкция компонента. |

## frontend/src/features

| Файл | Назначение |
|---|---|
| [Context.jsx](../frontend/src/features/Context.jsx) | Получение/просмотр погодных и событийных снимков, состояния источников, геообъекты и атрибуция. |
| [Evaluations.jsx](../frontend/src/features/Evaluations.jsx) | Отчёты, folds, all/peak метрики и сравнение факта с сезонной базой. |
| [Fleet.jsx](../frontend/src/features/Fleet.jsx) | Форма сценария выпуска с целевым заполнением, оборотом и резервом. |
| [Forecast.jsx](../frontend/src/features/Forecast.jsx) | Профили/границы дат, создание запуска, polling, сохранённые результаты, единые фильтры карты и графика. |
| [History.jsx](../frontend/src/features/History.jsx) | Выбор профиля и периода наблюдений, пространственный ряд, график и CSV. |
| [Occupancy.jsx](../frontend/src/features/Occupancy.jsx) | Создание ручного рейса, очередная остановка, измеренные высадки и таблица сохранённого баланса. |
| [README.md](../frontend/src/features/README.md) | Навигация и инструкция компонента. |

## frontend/tests

| Файл | Назначение |
|---|---|
| [client.test.js](../frontend/tests/client.test.js) | Node-тесты пагинации, авторизации/ошибок, пропусков, времени и CSV. |
| [README.md](../frontend/tests/README.md) | Навигация и инструкция компонента. |

## ml

| Файл | Назначение |
|---|---|
| [README.md](../ml/README.md) | Навигация и инструкция компонента. |

## ml/src

| Файл | Назначение |
|---|---|
| [README.md](../ml/src/README.md) | Навигация и инструкция компонента. |

## ml/src/tram_ml

| Файл | Назначение |
|---|---|
| [__init__.py](../ml/src/tram_ml/__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [baseline.py](../ml/src/tram_ml/baseline.py) | SeasonalNaive: предыдущая доступная неделя/год, без fit и без использования будущих наблюдений. |
| [context.py](../ml/src/tram_ml/context.py) | Расстояния и сопоставление внешних снимков по месту, времени и доступности на as_of. |
| [evaluation.py](../ml/src/tram_ml/evaluation.py) | Полные временные folds и MAE/WAPE с объяснимыми пустыми/нулевыми случаями. |
| [features.py](../ml/src/tram_ml/features.py) | Календарные признаки Москвы: час, день недели, месяц, выходной. |
| [README.md](../ml/src/tram_ml/README.md) | Навигация и инструкция компонента. |

## scripts

| Файл | Назначение |
|---|---|
| [check_docs.py](../scripts/check_docs.py) | Проверка локальных Markdown-ссылок и наличия назначения каждого файла в README своей папки. |
| [README.md](../scripts/README.md) | Навигация и инструкция компонента. |
| [start-component.ps1](../scripts/start-component.ps1) | Запуск одного локального компонента в текущем терминале с правильным рабочим каталогом. |

## tests

| Файл | Назначение |
|---|---|
| [__init__.py](../tests/__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [browser_server.py](../tests/browser_server.py) | Изолированный UI smoke: временная SQLite, публичные тестовые ключи, демо, отчёты и worker без .env. |
| [README.md](../tests/README.md) | Навигация и инструкция компонента. |
| [support.py](../tests/support.py) | Общие доверенные синтетические фикстуры и фиксированные часы тестов. |
| [test_aggregation.py](../tests/test_aggregation.py) | Взвешивание по времени/вместимости, границы интервалов и публикация estimated-экспорта. |
| [test_api.py](../tests/test_api.py) | Контракт всех базовых HTTP-операций, авторизация, ошибки, строгий JSON и полный forecast pipeline. |
| [test_bootstrap.py](../tests/test_bootstrap.py) | Миграции up/down и metadata, направление зависимостей, согласованность Python-зависимостей. |
| [test_context.py](../tests/test_context.py) | Фикстуры провайдеров, редактирование секретов из ошибок, as_of-признаки и импорт GeoJSON. |
| [test_domain_ml.py](../tests/test_domain_ml.py) | Предметные интервалы/ключи, сезонная база, folds и граничные случаи метрик. |
| [test_evaluation_pipeline.py](../tests/test_evaluation_pipeline.py) | Публикация полных day/month/year отчётов и CSV-пропусков. |
| [test_fleet.py](../tests/test_fleet.py) | Округление выпуска, резерв, нулевой спрос и контракт сценарного API. |
| [test_occupancy.py](../tests/test_occupancy.py) | Три сценария, баланс, измеренные высадки, replay/конфликты и контракт API рейсов. |
| [test_postgres.py](../tests/test_postgres.py) | Реальная конкурентность PostgreSQL: публикация, идемпотентность, SKIP LOCKED, fencing и события рейса. |
| [test_publication.py](../tests/test_publication.py) | Атомарная публикация, повторы/ошибки/откат, demo и все горизонты. |
| [test_repository.py](../tests/test_repository.py) | SQL-проекции, очереди, фильтры, временная валидность сети и пагинация. |

## sources

| Файл | Назначение |
|---|---|
| [README.md](../sources/README.md) | Оригиналы источников: фактические образцы, паспорт, получение 624/62743 и передача в data. |

## data

| Файл | Назначение |
|---|---|
| [README.md](../data/README.md) | Конкретные файлы демо, будущая структура обработки, очистка, публикация и переход к обучению. |

## models

| Файл | Назначение |
|---|---|
| [README.md](../models/README.md) | Будущий состав артефакта модели, проверка, версионирование и подключение к worker. |
