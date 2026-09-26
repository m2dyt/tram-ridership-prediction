# Backend

FastAPI, сценарии приложения и PostgreSQL. Запуск из корня: `python -m tram.cli serve`; отдельно `python -m tram.cli worker`. Миграции: `python -m tram.cli migrate`. [Устройство решения](../docs/ARCHITECTURE.md).

## Что происходит в backend

| Вход | Обработка | Результат |
|---|---|---|
| Каталог prepared bundle | `cli/commands` → `application.publication` → SQL-адаптер | Неизменяемая ревизия данных, сеть и временные ряды в PostgreSQL. |
| POST запроса прогноза | HTTP проверяет токен/контракт; `ForecastService` проверяет профиль, время и модель | Задание в очереди и `run_id`; вычисление выполняет отдельный worker. |
| Задание worker | Чтение истории на `as_of` → порт `Predictor` → сохранение точек | Статус завершения и прогноз для API/карты. |
| Событие рейса | Сверка следующей остановки → чистый баланс → транзакция журнала | Сохранённый остаток людей и история переходов. |
| Запрос погоды/событий | Адаптер HTTP → нормализация → снимок | Доступный контекст либо явное состояние `unavailable`. |

Точки сборки и входа: [src/tram](src/tram/README.md). [domain](src/tram/domain/README.md) содержит формулы; [application](src/tram/application/README.md) — сценарии и порты; [infrastructure](src/tram/infrastructure/README.md) — SQL/HTTP/файлы; [api](src/tram/api/README.md) — HTTP-контракт. Зависимости направлены к domain/application, реализации внедряются в `composition.py`.

## Что делать дальше здесь

Для метро 624/62743 уже добавлены проверка файлов в `infrastructure/metro_files.py`, чистая подготовка в `application/metro.py` и отдельная сборка CLI в `metro_commands.py`. [Команды и результаты](../docs/METRO_PIPELINE.md) работают без настроек БД. Для других реальных схем добавить свой адаптер в infrastructure, затем сценарий и CLI. Не помещать обработку Excel/HTTP в domain. Для обученной модели нужен адаптер артефакта через `Predictor`, согласованный источник признаков и регистрация нового метода. Сейчас `publication.py`, `service.py` и `worker.py` допускают только `seasonal_naive_v1`; `composition.py` подключает `SeasonalNaive`.

Обучение выполняется отдельным процессом, API лишь ставит задания прогнозирования. `application/evaluation.py` сейчас оценивает базу; сравнение с кандидатом должно вызывать два разных предиктора. Порядок интеграции обученной модели — в [глобальном плане проекта](../00_ГЛОБАЛЬНЫЙ_ПЛАН_К_ЭТАЛОНУ.md).

## Проверка результата изменения

Из корня: `python -m pytest -q tests/test_api.py tests/test_bootstrap.py`. Для правок очереди/транзакций также выполнить PostgreSQL-проверки по [TESTING.md](../docs/TESTING.md). При изменении HTTP синхронно обновить корневой `openapi.yaml` и контрактный тест. При изменении хранения — новая миграция в [migrations](migrations/README.md); уже применённые миграции не редактировать вместо новой.

## Файлы

| Файл | Назначение |
|---|---|
| README.md | Навигация по дочерним компонентам. |

## Подпапки

- [migrations](migrations/README.md).
- [src](src/README.md).
