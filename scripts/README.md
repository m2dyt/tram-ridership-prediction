# Служебные команды

Инструменты запуска и проверки документации. Выполнять из репозитория; они не создают расписаний и не меняют системные политики.

## Как пользоваться

`./scripts/start-component.ps1 api` запускает API в текущем терминале; значения `worker` и `frontend` запускают соответствующий компонент. Остановка — Ctrl+C. Это удобная оболочка над командами установки/запуска из главного README, а не менеджер служб и не процесс обучения.

`python scripts/check_docs.py` читает поддерживаемые Git-файлы и Markdown: проверяет существование локальных ссылок и упоминание файлов в README их папок. Результат — список ошибок либо число проверенных файлов. Он **не проверяет доступность внешних сайтов, якоря разделов или смысл инструкции**. Результаты отдельной сетевой проверки датасетов записаны в [DATA_LINK_CHECKS.json](../docs/DATA_LINK_CHECKS.json).

## Файлы

| Файл | Назначение |
|---|---|
| [benchmark_inference.py](benchmark_inference.py) | Замер задержки (`p50`, `p90`, `p95`, `p99`), пропускной способности (RPS) и памяти для `ArtifactPredictor` и `SeasonalNaive` с записью в `benchmarks/latest.json`. |
| [validate_submission.py](validate_submission.py) | Строгая валидация сабмита: 14 640 строк, 10 маршрутов, маршрут 5 == 0, разделитель `;`, отсутствие NaN/inf/пропусков, сравнение с baseline. |
| [fetch_weather_2025.py](fetch_weather_2025.py) | Выгрузка фактической почасовой погоды Москвы за 2025 год через Open-Meteo Archive API в `data/weather_hourly_2025.csv`. |
| [generate_calendar_2025.py](generate_calendar_2025.py) | Генерация производственного календаря РФ за 2025 год (постановление Правительства № 1335) в `data/calendar_2025.csv`. |
| [check_docs.py](check_docs.py) | Проверка локальных Markdown-ссылок и наличия назначения каждого файла в README своей папки. |
| [smoke_model_serving.py](smoke_model_serving.py) | Сквозная проверка работающего стека: поднимает `uvicorn` и `tram worker` против `TRAM_DATABASE_URL`, проходит `/health`, вход → `/auth/me` → refresh → logout (и отказ после них), реестр `/models` и прогноз по каждому профилю набора; с `--expect-bundle` требует, чтобы часовые запуски были закреплены за бандлом и совпадали с его прямым вызовом. Код выхода 0 только если всё прошло. |
| [prepare_tram_challenge.py](prepare_tram_challenge.py) | Аудит, проверка схемы, расчёт SHA-256 хешей конкурсных датасетов и генерация provenance.json и manifest.json. |
| [download_sources.py](download_sources.py) | Скачивание открытых API (погода, события) и импорт выгрузок data.mos.ru с формированием provenance.json. |
| [start-component.ps1](start-component.ps1) | Запуск одного локального компонента в текущем терминале с правильным рабочим каталогом. |

