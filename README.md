# Трамвай · прогноз загрузки

Рабочий исследовательский прототип: **FastAPI + PostgreSQL + отдельный worker, React на JavaScript + Vite + OpenStreetMap/Leaflet**. Есть сезонный прогноз на сутки, месяц и год без обучения, история и отчёты качества, расчёт остатка пассажиров по вагонам, внешние снимки погоды/мероприятий, импорт геоданных и сценарный калькулятор выпуска.

Обучение моделей не выполнялось. Демонстрационные маршруты и пассажиропоток синтетические, это явно указано в API и интерфейсе. Погода Open-Meteo проверена живым запросом. Реальные валидации/телематика и сеть Москвы пока не предоставлены; точность на реальных пассажирах не измерена. [Полная таблица готовности и ограничений](docs/STATUS.md).

## Быстрый запуск на Windows / PowerShell

Нужны Python **3.12**, Node.js **22.12+ (ветка 22) или 24+**, Docker Desktop для PostgreSQL. Выполнять из корня:

```powershell
cd C:\proga\projects\tram-ridership-prediction
```

**1. Создать venv, если его ещё нет:**

```powershell
py -3.12 -m venv .venv
```

**2. Активировать venv — отдельная команда:**

```powershell
.\.venv\Scripts\Activate.ps1
```

**3. Скачать и установить библиотеки — отдельная команда:**

```powershell
python -m pip install -r requirements.txt -e .
```

В проекте **один requirements.txt**. Он содержит Python-зависимости приложения и инструменты разработки; `-e .` подключает локальные пакеты tram и tram_ml. package.json/package-lock.json относятся к отдельному JavaScript frontend. Рабочую .venv пересоздавать не надо. Если активация ограничена политикой PowerShell, можно выполнять команды через `.\.venv\Scripts\python.exe`, не меняя политику системы.

**4. Создать конфигурацию только при отсутствии .env:**

```powershell
python -m tram.cli init-config
```

Генерируются случайный пароль БД и разные ключи viewer/operator/cursor. Существующий .env не перезаписывается. Ключи нужны для входа в интерфейс и Swagger; храните их локально. Шаблон параметров: [.env.example](.env.example).

**5. Поднять БД и применить миграции:**

```powershell
docker compose up -d --wait db
python -m tram.cli migrate
```

БД проекта доступна на 127.0.0.1:15433. Она отделена от тестовой БД на 15434. Если .env создавался ранее, сохраняйте его пароль и порт; не заменяйте пароль у уже заполненного Docker volume.

**6. Подготовить демонстрационные данные:**

```powershell
python -m tram.cli demo data/demo-complete
python -m tram.cli publish data/demo-complete
python -m tram.cli replay-trip data/demo-complete/trip-plan.json data/demo-complete/trip-events.jsonl
```

Если демоданные уже созданы, повторять demo в существующий каталог не нужно. Для нового дня выбрать новое имя каталога. Публикация одинакового содержимого и повтор журнала безопасны. [Отчёты, погода, импорт CSV/GeoJSON, экспорт наполненности](docs/OPERATIONS.md).

**7. Установить frontend:**

```powershell
cd frontend
npm.cmd ci
cd ..
```

**8. Запустить три компонента в отдельных терминалах:**

Терминал API из корня с активированной .venv:

```powershell
python -m tram.cli serve
```

Терминал worker из корня с активированной .venv:

```powershell
python -m tram.cli worker
```

Терминал frontend:

```powershell
cd frontend
npm.cmd run dev
```

Открыть **http://127.0.0.1:5173**. Ввести значение TRAM_OPERATOR_TOKEN из своего .env для создания расчётов либо TRAM_VIEWER_TOKEN для чтения. Ключ хранится только в памяти вкладки. Swagger — **http://127.0.0.1:8000/docs**, готовность — **http://127.0.0.1:8000/api/v1/health**. В Swagger нажать Authorize и вставить токен, без дополнительного слова Bearer.

Альтернатива командам отдельных терминалов: `./scripts/start-component.ps1 api`, `worker` или `frontend`. Скрипт запускает один компонент в текущем терминале; Ctrl+C останавливает его. После изменения Python-кода перезапустить API/worker. Frontend в dev обновляется автоматически; изменение файлов может сбросить вход.

## Сборка интерфейса и единый адрес

```powershell
cd frontend
npm.cmd run build
cd ..
python -m tram.cli serve
```

Если frontend/dist существует на момент запуска, FastAPI раздаёт его на **http://127.0.0.1:8000/**. API и Swagger продолжают работать по своим путям; отдельный Vite для готовой сборки не нужен. Worker остаётся отдельным процессом. После изменения frontend пересобрать dist. `npm run preview` предназначен для просмотра статической сборки и не настраивает API-прокси.

## Docker как альтернативный способ

Dockerfile собирает frontend и backend, Compose запускает миграции перед API/worker:

```powershell
docker compose up -d --build api worker
```

Перед этим остановить локальный API на 8000, чтобы не было конфликта портов. Для импорта данных в контейнер:

```powershell
docker compose run --rm -v "${PWD}/data:/imports:ro" migrate python -m tram.cli publish /imports/demo-complete
```

Локальная установка .venv проверена. Контейнерная сборка требует доступных npm/PyPI/registry; её фактический результат описан в [журнале](docs/IMPLEMENTATION_LOG.md). Не удалять postgres-data для обычного перезапуска.

## Как устроено решение

1. Исходные агрегаты проходят проверку и публикуются как неизменяемая ревизия. Неполные интервалы, неизвестные связи, дубли и будущая доступность отклоняются. Пропуски не превращаются в нули.
2. API создаёт задание. Worker использует сезонную базу: предыдущую доступную неделю для суток/месяца, предыдущий год для годового прогноза. Расчёт не обучает модель и не обращается к внешним API во время чтения.
3. Карта и график привязаны к одному run_id, пространственному ряду и интервалу. Доступные показатели/горизонты определяет опубликованный профиль, а не жёсткий список frontend.
4. Отдельный баланс рейса переносит группы пассажиров между остановками. Высадка оценивается по трём сценариям длительности либо задаётся измерением. Состояние и журнал сохраняются транзакционно. Наполненность и доля заполнения усредняются по времени проездов, не суммируются по вагонам.
5. Погода, мероприятия и московские геообъекты хранятся снимками с available_at. Признаки подготовлены для будущей модели; сезонный прогноз пока их не использует.
6. Оценка на истории использует сведения, доступные на момент отсечки. Отчёты содержат полные временные горизонты, MAE/WAPE и явные исключения.

Идея: сначала получить проверяемый поток данных и воспроизводимые расчёты, затем сравнивать обученные модели с честной базой. [Подробная архитектура и правила расширения](docs/ARCHITECTURE.md).

## Где что находится

| Папка/файл | Назначение |
|---|---|
| [backend](backend/README.md) | Python-приложение, HTTP, сценарии, domain и инфраструктурные адаптеры |
| [ml](ml/README.md) | Сезонная база, признаки и временная оценка без обучения |
| [frontend](frontend/README.md) | React/JSX, API-клиент, карта, графики и формы |
| [tests](tests/README.md) | Domain, API, публикация, PostgreSQL, ML и изолированный browser smoke |
| [scripts](scripts/README.md) | Запуск компонентов и проверка документации |
| [docs](docs/README.md) | Архитектура, сценарии, форматы, источники, статус и ревью |
| [openapi.yaml](openapi.yaml) | Исполняемый контракт Swagger; соответствует HTTP-обработчикам |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Исходный план проекта и дополнительные требования |
| [docs/DELIVERY_PLAN.md](docs/DELIVERY_PLAN.md) | План текущей поставки без обучения |
| [pyproject.toml](pyproject.toml) | Python-пакеты, совместимость, зависимости, CLI, pytest/Ruff |
| [requirements.txt](requirements.txt) | Единый список установки Python и инструментов |
| [alembic.ini](alembic.ini) | Настройка миграций; секретный URL берётся из .env |
| [compose.yaml](compose.yaml), [Dockerfile](Dockerfile) | БД, миграции, API/worker, многослойная сборка интерфейса |
| [.github/workflows/checks.yml](.github/workflows/checks.yml) | CI: Python/PostgreSQL и frontend |
| [.gitignore](.gitignore), [.dockerignore](.dockerignore), [.gitattributes](.gitattributes), [.python-version](.python-version) | Исключения секретов/артефактов, контекст Docker, окончания строк, версия Python |

В каждой папке с исходным кодом есть README с назначением каждого файла. [Полная карта файлов](docs/FILE_MAP.md). Создаваемые data/, logs/, .venv/, node_modules/, dist/ и .env исключены из Git.

## Проверка установки

```powershell
python -m tram.cli doctor
python -m pip check
docker compose --profile test up -d --wait test-db
```

Отдельно задать тестовую БД и выполнить проверки:

```powershell
$env:TRAM_TEST_DATABASE_URL = 'postgresql+psycopg://tram:tram-test-only@127.0.0.1:15434/tram_test'
python -m pytest -q
python -m ruff check backend ml tests scripts
python -m ruff format --check backend ml tests scripts
python scripts/check_docs.py
```

```powershell
cd frontend
npm.cmd run test
npm.cmd run build
npm.cmd run format:check
```

Без TRAM_TEST_DATABASE_URL интеграционные тесты PostgreSQL получают SKIPPED — это намеренно. [Полная инструкция проверок и изолированного UI-стенда](docs/TESTING.md).

## Следующие входы для работы с реальным городом

Нужны файлы валидаций/телематики со словарём полей, версии маршрутов и расписания, ID вагонов/рейсов, вместимости и независимые наблюдения для проверки восстановленных высадок. Также нужны доступные выгрузки Москвы и при необходимости ключи WeatherAPI/Timepad. После их появления: отдельный ETL под реальные схемы, аудит временной доступности, подготовка ряда occupancy, затем обучение, калибровка интервалов и сравнение на отложенных периодах. Автоматические диспетчерские решения не принимаются.
