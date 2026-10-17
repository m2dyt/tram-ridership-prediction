# Служебные команды (scripts/)

Инструменты автоматизации, бенчмаркинга, загрузки данных и проверки документации. Выполнять из корня репозитория.

---

## 1. Сценарии использования

- `./scripts/start-component.ps1 api` запускает API в текущем терминале; аргументы `worker` и `frontend` запускают соответствующий компонент. Остановка — Ctrl+C.
- `sh scripts/start-stack.sh` собирает и поднимает полный Docker-стек с PostgreSQL, импортом конкурсных меток, обучением модели, API, worker и фронтендом.
- `python scripts/check_docs.py` выполняет валидацию локальных Markdown-ссылок и проверяет упоминание каждого файла в README соответствующей папки.

---

## 2. Каталог скриптов

| Файл | Назначение |
|---|---|
| [benchmark_inference.py](benchmark_inference.py) | Замер задержки (`p50`, `p90`, `p95`, `p99`), пропускной способности (RPS) и памяти для `ArtifactPredictor` и `SeasonalNaive` с записью в `benchmarks/latest.json`. |
| [benchmark_api.py](benchmark_api.py) | Замер задержки и RPS для полного пути API: `uvicorn` + `tram worker` против PostgreSQL (`POST /forecast-runs` → поллинг → `GET .../points`). |
| [validate_submission.py](validate_submission.py) | Строгая валидация сабмита: 14 640 строк, 10 маршрутов, маршрут 5 == 0, разделитель `;`, отсутствие NaN/inf/пропусков, сравнение с baseline. |
| [extract_tram_network_features.py](extract_tram_network_features.py) | Расчет пространственных фичей маршрутов, расчет доли обособленности путей (`route_segregated_ratio`) из `data/tramlanes.geojson`, нормализация остановок. |
| [extract_stops.js](extract_stops.js) | Node.js утилита извлечения остановок из исходных GeoJSON и CSV-справочников. |
| [fetch_mosru_data.js](fetch_mosru_data.js) | Скрипт выгрузки справочников транспорта и остановок с портала открытых данных Москвы. |
| [fetch_route_geom.js](fetch_route_geom.js) | Скрипт получения геометрии маршрутов общественного транспорта. |
| [fetch_weather_2025.py](fetch_weather_2025.py) | Выгрузка фактической почасовой погоды Москвы за 2025 год через Open-Meteo Archive API в `data/weather_hourly_2025.csv`. |
| [generate_calendar_2025.py](generate_calendar_2025.py) | Генерация производственного календаря РФ за 2025 год (постановление Правительства № 1335) в `data/calendar_2025.csv`. |
| [check_docs.py](check_docs.py) | Проверка локальных Markdown-ссылок и наличия назначения каждого файла в README своей папки. |
| [smoke_model_serving.py](smoke_model_serving.py) | Сквозная проверка работающего стека: аутентификация, реестр моделей, генерация прогноза и валидация инференса. |
| [prepare_tram_challenge.py](prepare_tram_challenge.py) | Аудит, проверка схемы, расчёт SHA-256 хешей конкурсных датасетов и генерация provenance.json и manifest.json. |
| [build_competition_bundle.py](build_competition_bundle.py) | Подготовка почасовых наблюдений и сети маршрутов для импорта в PostgreSQL. |
| [import-dataset.sh](import-dataset.sh) | Генерация API-бандла и публикация ревизии конкурсных меток в базу данных. |
| [train-model.sh](train-model.sh) | Обучение CPU-модели по меткам и запись версионированного бандла в том Docker. |
| [bootstrap-operator.py](bootstrap-operator.py) | Создание локального оператора на пустой базе данных с паролем по умолчанию. |
| [start-stack.sh](start-stack.sh) | Полная сборка, миграции, импорт, обучение, запуск сервисов и проверка счетчиков PostgreSQL. |
| [download_sources.py](download_sources.py) | Скачивание открытых API (погода, события) и импорт выгрузок data.mos.ru. |
| [start-component.ps1](start-component.ps1) | Запуск отдельного локального компонента (api, worker, frontend) в текущем PowerShell-терминале. |
