# Проверки и тестовый стенд

Тесты не обучают модели, не требуют API-ключей источников и не изменяют рабочие таблицы. PostgreSQL-тесты создают собственную случайную схему и удаляют только её. Проверки внешних API по умолчанию используют фикстуры/MockTransport.

## Python и PostgreSQL

Из корня, в активной `.venv`:

```powershell
docker compose --profile test up -d --wait test-db
```

Затем:

```powershell
$env:TRAM_TEST_DATABASE_URL = 'postgresql+psycopg://tram:tram-test-only@127.0.0.1:15434/tram_test'
python -m pytest -q
python -m ruff check backend ml tests scripts
python -m ruff format --check backend ml tests scripts
python -m pip check
python -m alembic check
python scripts/check_docs.py
```

`alembic check` использует рабочую БД из `.env`, проверяя только расхождения схемы; перед ним применить `python -m tram.cli migrate`. **SKIPPED** у PostgreSQL-тестов означает отсутствие переменной `TRAM_TEST_DATABASE_URL`, а не поломку pytest. Для полного прогона нужны и БД, и эта переменная в том же терминале.

## Проверка API и миграций на рабочей PostgreSQL

Перед выпуском изменений auth, миграций или обслуживания модели — три шага, все на настоящей PostgreSQL (не SQLite).

1. **Полный набор тестов с PostgreSQL** — как в разделе выше. Все тесты `tests/test_postgres.py` должны выполниться, а не попасть в SKIPPED.
2. **Миграции на пустой базе туда и обратно.** Отдельная база, чтобы не трогать рабочую:

   ```bash
   docker compose exec -T test-db psql -U tram -d tram_test -c "DROP DATABASE IF EXISTS tram_migcheck;" -c "CREATE DATABASE tram_migcheck;"
   export TRAM_DATABASE_URL='postgresql+psycopg://tram:tram-test-only@127.0.0.1:15434/tram_migcheck'
   python -m alembic upgrade head && python -m alembic downgrade base && python -m alembic upgrade head
   python -m alembic downgrade 0003 && python -m alembic upgrade 0004 && python -m alembic upgrade head
   python -m alembic check
   ```

   После `downgrade base` в схеме не остаётся таблиц приложения; `alembic check` должен ответить `No new upgrade operations detected.`
3. **Сквозная проверка работающего стека** против `TRAM_DATABASE_URL` из `.env` с опубликованным набором:

   ```bash
   python scripts/smoke_model_serving.py --dataset <dataset_revision_id>
   python scripts/smoke_model_serving.py --dataset <набор с маршрутами-номерами> --expect-bundle <версия>
   ```

   Скрипт сам поднимает `uvicorn` и `tram worker`, проверяет `/health`, создаёт operator статическим токеном и проходит вход → `/auth/me` → refresh (в ответе `role` и `user`, старый refresh-токен после ротации отклоняется) → logout → refresh после logout (401), читает `/models` и активную модель, затем создаёт по запуску на каждый доступный профиль. С `--expect-bundle` часовые запуски должны быть закреплены за этим бандлом, а отданные значения — совпадать с прямым вызовом бандла; остальные профили — на `seasonal_naive_v1`. Бандл умеет только номера конкурсных маршрутов (`1`…`50`): на демо-наборе с `demo-route-01` он честно не используется, это видно в `run.warnings`. Код выхода 0 — только если прошли все проверки.

## Frontend

```powershell
cd frontend
npm.cmd ci
npm.cmd run test
npm.cmd run build
npm.cmd run format:check
```

Тесты клиента проверяют пагинацию, сохранение фильтров и авторизации, обработку ошибок, разрывы графика и безопасное формирование CSV. Ручной smoke в браузере проверяет вход, создание/ожидание прогноза, карту/график, историю, оценки, журнал рейса и внешний снимок.

## Изолированный browser smoke без PostgreSQL

Терминал 1 из корня:

```powershell
python -m tests.browser_server
```

Терминал 2:

```powershell
cd frontend
$env:TRAM_API_PROXY = 'http://127.0.0.1:8002'
npm.cmd run dev -- --port 5174
```

Открыть http://127.0.0.1:5174. Публичный **только тестовый** ключ: `browser-operator-browser-operator-browser-operator-`. Viewer: `browser-viewer-browser-viewer-browser-viewer-`. Сервер создаёт собственную временную SQLite-базу, демо, рейс, отчёты и worker; .env и рабочую БД не читает. При нормальной остановке Ctrl+C временный каталог очищается. Не выставлять этот сервер наружу и не применять эти ключи в рабочей конфигурации.

## Что проверяют тесты

- Инварианты времени, сетки, пространственных ключей и массы пассажиров.
- Честное отсутствие предсказания при недоступной опорной истории; недоступность будущих источников.
- Публикация целиком либо откат, неизменяемость версий и повторные команды.
- Конкурентные запросы, lease/fencing worker, повтор события рейса и восстановление его состояния.
- HTTP-статусы, авторизация, JSON/OpenAPI, отсутствие секретов в ошибках.
- Полные день/месяц/год в backtesting, публикация отчётов, пустые/нулевые метрики.
- Разные вместимости, среднее по времени и экспорт наполненности как estimated.
- Направление зависимостей domain/application/ML и актуальность миграций.

Нагрузочный тест на миллионах реальных сырых строк, live-stream транспортных данных, обучение и независимая проверка точности пока не выполнены.
