> Актуальный полный запуск backend + frontend: [корневой README](../README.md). Команды подготовки новых источников и оценки: [OPERATIONS.md](OPERATIONS.md). Ниже — подробности Python-окружения.

# Установка в Windows / PowerShell

Используем Python 3.12 и отдельное окружение `.venv`. Все библиотеки приложения, тестов и форматирования перечислены в одном `requirements.txt`. Глобальные пакеты менять не нужно.

## 1. Перейти в репозиторий

```powershell
cd C:\proga\projects\tram-ridership-prediction
```

## 2. Создать виртуальное окружение

Выполняется при первой установке. Если `.venv` уже создано и работает, переходи к следующему шагу.

```powershell
py -3.12 -m venv .venv
```

Если команда `py` недоступна, на этой машине установлен Python по пути:

```powershell
& 'C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe' -m venv .venv
```

## 3. Активировать окружение

Эта команда выполняется при открытии нового терминала:

```powershell
.\.venv\Scripts\Activate.ps1
```

Проверить, какой Python используется:

```powershell
python -c "import sys; print(sys.executable)"
```

Ожидаемый путь: `C:\proga\projects\tram-ridership-prediction\.venv\Scripts\python.exe`.

## 4. Скачать и установить зависимости

После активации выполни отдельно:

```powershell
python -m pip install -r requirements.txt -e .
```

`-r requirements.txt` устанавливает библиотеки и инструменты разработки. `-e .` подключает пакеты проекта `tram` и `tram_ml`, чтобы изменения исходного кода были доступны сразу. Повторная установка безопасна: уже подходящие версии pip оставит установленными.

Предварительное обновление pip необязательно. Если оно потребуется:

```powershell
python -m pip install --upgrade pip
```

## 5. Проверить установку и код

```powershell
python -m pip check
python -m tram.cli doctor
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
```

`pip check` должен вывести `No broken requirements found`, а `doctor` — `OK` напротив каждой библиотеки. Эти команды доступны Codex через `.venv\Scripts\python.exe`; передавать окружение отдельно не нужно.

Проверки PostgreSQL запускаются отдельно, если задан `TRAM_TEST_DATABASE_URL`. Без него они отмечаются как `skipped`; быстрые тесты используют SQLite. Пример для отдельной локальной тестовой БД:

```powershell
docker compose --profile test up -d --wait test-db
$env:TRAM_TEST_DATABASE_URL = 'postgresql+psycopg://tram:tram-test-only@127.0.0.1:15434/tram_test'
python -m pytest -q
```

Перед первым запуском Compose выполнить `python -m tram.cli init-config`, если `.env` ещё нет. Адрес выше относится к сервису `test-db` из Compose. Каждый PostgreSQL-тест создаёт отдельную случайную схему и удаляет только её после проверки. Переменная действует только в текущем PowerShell; в новом окне её нужно задать снова.

## Если активация заблокирована PowerShell

Можно использовать окружение напрямую без изменения политики выполнения:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

## Доступные команды проекта

```powershell
python -m tram.cli --help
python -m tram.cli doctor
```

Для миграций и worker нужна доступная PostgreSQL и переменная `TRAM_DATABASE_URL`. Команды запускаются из корня репозитория:

```powershell
$env:TRAM_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE'
python -m tram.cli migrate
python -m tram.cli worker --once
```

Замени `USER`, `PASSWORD`, `HOST`, `PORT`, `DATABASE` своими значениями. `worker --once` обрабатывает не более одного уже созданного задания. Без заданий он завершится без расчёта. Ни установка, ни эти команды не запускают обучение модели.

**Текущее состояние:** готовы предметная логика, сценарии, SQL-адаптер, миграции, HTTP API со Swagger, импорт подготовленных агрегатов, worker и сезонная база без обучения. Полная последовательность запуска с PostgreSQL и демоданными — в [README](../README.md). Подготовка сырых исходных файлов и обучение остаются отдельными этапами.

Завершить работу в активированном окружении:

```powershell
deactivate
```

Если при скачивании возникает таймаут, проверь доступ к `pypi.org` и `files.pythonhosted.org`, затем повтори установку. Переустановка глобального Python не нужна. Диапазоны в `requirements.txt` не являются точным lock-файлом.
