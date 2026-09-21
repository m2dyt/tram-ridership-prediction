# Пакет tram

Точки входа и сборка зависимостей находятся здесь; предметные правила — в domain, сценарии — application, внешние технологии — infrastructure/api.

## Файлы

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [cli.py](cli.py) | Основные команды: диагностика, конфигурация, demo/publish, миграции, API и worker; делегирование дополнительных команд. |
| [commands.py](commands.py) | CLI для снимков, GeoJSON, CSV, replay, backtesting и экспорта наполненности; соединяет адаптеры со сценариями. |
| [metro_commands.py](metro_commands.py) | Сборка prepare-metro/evaluate-metro: файлы → подготовка/квартальная база → результаты; без Settings/БД. |
| [composition.py](composition.py) | Точка сборки приложения: настройки, SQL, часы, порты, HTTP, ML и раздача frontend/dist. |

## Подпапки

- [api](api/README.md).
- [application](application/README.md).
- [domain](domain/README.md).
- [infrastructure](infrastructure/README.md).
