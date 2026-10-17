# demo-bundle — демонстрационный подготовленный бандл данных

Набор синтетических данных и шаблонов запросов для демонстрационного режима и автоматических тестов API.

---

## Файлы

| Файл | Назначение |
|---|---|
| [context-request.json](context-request.json) | Шаблон запроса внешнего контекста (погода, события). |
| [evaluation-origins.json](evaluation-origins.json) | Отсечки дат для исторической валидации на демо-данных. |
| [manifest.json](manifest.json) | Манифест ревизии данных: профили, маршруты, временные диапазоны и контрольные суммы. |
| [observations.jsonl](observations.jsonl) | Синтетический поток наблюдений пассажиропотока по интервалам. |
| [request-day.json](request-day.json) | Пример запроса прогноза с суточным горизонтом (`horizon=day`). |
| [request-month.json](request-month.json) | Пример запроса прогноза с месячным горизонтом (`horizon=month`). |
| [request-year.json](request-year.json) | Пример запроса прогноза с годовым горизонтом (`horizon=year`). |
| [trip-events.jsonl](trip-events.jsonl) | Журнал остановочных событий (входы/выходы) для симуляции рейса. |
| [trip-plan.json](trip-plan.json) | Маршрутный план движения вагона для проверки баланса пассажиров. |
