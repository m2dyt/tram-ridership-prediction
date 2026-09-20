# Документация проекта

Начать с [корневого README](../README.md), затем ARCHITECTURE → OPERATIONS → TESTING. STATUS фиксирует реальные границы готовности; IMPLEMENTATION_LOG — историю шагов и ревью. Сведения из исходного ТЗ трактуются как требования, а не как разрешение на обучение или внешнюю публикацию.

## Файлы

| Файл | Назначение |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Границы слоёв, поток данных, версии/время, очередь, баланс пассажиров и расширение. |
| [DATA_FORMAT.md](DATA_FORMAT.md) | Контракт prepared bundle: manifest, ряд, временная сетка, JSONL и происхождение. |
| [DATA_SOURCES.md](DATA_SOURCES.md) | Выбор внешних источников, официальные ссылки, условия доступности и ограничения. |
| [DELIVERY_PLAN.md](DELIVERY_PLAN.md) | План текущей реализации без обучения, порядок шагов и критерии проверки. |
| [FILE_MAP.md](FILE_MAP.md) | Полная карта поддерживаемых файлов и ссылок на папки. |
| [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) | История выполненных шагов: план → реализация → проверки → ревью. |
| [LOCAL_SETUP.md](LOCAL_SETUP.md) | Подробности Python/venv и диагностики локального окружения. |
| [OPERATIONS.md](OPERATIONS.md) | Готовые команды демо, оценки, источников, GeoJSON/CSV, replay, экспорта и калькулятора. |
| [PASSENGER_OCCUPANCY.md](PASSENGER_OCCUPANCY.md) | Математическая постановка восстановления высадок и остатка, сценарии и критерии валидации. |
| [STATUS.md](STATUS.md) | Сопоставление требований ТЗ с кодом и явные ограничения данных, источников и эксплуатации. |
| [TESTING.md](TESTING.md) | Полный запуск тестов без skip, frontend и временный browser smoke. |

## Подпапки

- [decisions](decisions/README.md).
