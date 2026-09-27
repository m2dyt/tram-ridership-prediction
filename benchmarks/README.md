# Результаты бенчмарков производительности

Каталог для сохранения отчётов замера производительности: инференса предиктора в процессе и полного серверного пути.

## Запуск бенчмарков

```powershell
# Прямые вызовы Predictor в процессе (без HTTP, без БД); память — только свой процесс.
python scripts/benchmark_inference.py --iterations 10

# Полный путь: настоящие uvicorn + tram worker против реальной PostgreSQL,
# HTTP POST /forecast-runs -> поллинг статуса -> GET .../points. Требует
# применённые миграции и опубликованный набор с доступным профилем
# (см. docs/OPERATIONS.md); psutil — pip install -e ".[benchmark]".
python scripts/benchmark_api.py --iterations 15
```

Оба скрипта пишут в один `latest.json`: `benchmark_inference.py` — ключ `scenarios`, `benchmark_api.py` — ключ `server_scenario`; повторный запуск одного не затирает результат другого. `end_to_end_ms` серверного сценария включает реальный интервал опроса воркера (`TRAM_POLL_SECONDS`, по умолчанию 2 с) — это ожидаемая часть замера, не следует путать со стоимостью самого расчёта (`submit_latency_ms`/`read_points_ms` изолируют её).

## Файлы

| Файл | Назначение |
|---|---|
| [latest.json](latest.json) | Последний отчёт: `scenarios` — квантили задержки/RPS/памяти прямого вызова предиктора; `server_scenario` — тот же набор метрик для полного пути API → worker → PostgreSQL под нагрузкой. |
