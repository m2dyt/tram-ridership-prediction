# Внешние адаптеры

SQL, файловые форматы, HTTP, конфигурация и контракт. Здесь переводятся внешние данные в документы приложения; предметная формула не должна зависеть от поставщика.

## Файлы

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Маркер Python-пакета; не открывает БД, сеть и не запускает процессы при импорте. |
| [bundles.py](bundles.py) | Чтение и структурная проверка manifest.json и последовательного observations.jsonl. |
| [context_store.py](context_store.py) | Запись и чтение неизменяемых снимков, фильтры provider/kind и пагинация. |
| [contract.py](contract.py) | Загрузка OpenAPI, JSON Schema, строгий JSON без дубликатов ключей и нечисловых NaN. |
| [csv_import.py](csv_import.py) | Потоковое преобразование точного CSV-формата агрегатов в prepared bundle. |
| [database.py](database.py) | SQLAlchemy-модели, UTC timestamp, engine/session factory и ограничения таблиц. |
| [demo.py](demo.py) | Синтетические данные текущей даты, сеть из четырёх остановок, запросы, план/журнал рейса и отсечки оценки. |
| [evaluation.py](evaluation.py) | Выборка фактов и транзакционная публикация проверенных по контракту отчёта и точек оценки. |
| [geo_import.py](geo_import.py) | Импорт WGS84 Point GeoJSON Москвы с явными полями, проверками координат/ID и SHA-256. |
| [publication.py](publication.py) | SQL-публикация набора одной транзакцией, хеширование потока, пакетные вставки и блокировки повторов. |
| [repository.py](repository.py) | SQL-чтение версий/точек/отчётов, очередь, идемпотентность запросов, lease/fencing и публикация прогнозов. |
| [runtime.py](runtime.py) | Системные часы и подписанные HMAC курсоры пагинации. |
| [settings.py](settings.py) | Типизированные TRAM_* настройки из .env/окружения; SecretStr и проверка ключей. |
| [sources.py](sources.py) | Ограниченные HTTP-клиенты Open-Meteo, WeatherAPI, KudaGo, Timepad и нормализация ответов без утечки ключей. |
| [trips.py](trips.py) | Постоянное состояние рейсов и журнал checkpoints, PostgreSQL-блокировки по trip_id. |
