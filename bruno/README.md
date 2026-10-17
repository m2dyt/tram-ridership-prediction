# bruno/ — коллекция запросов API

Коллекция автоматизированных запросов для тестирования REST API системы в приложении [Bruno](https://www.usebruno.com/).

---

## Файлы коллекции

| Файл | Метод и путь | Назначение |
|---|---|---|
| [bruno.json](bruno.json) | — | Конфигурация проекта Bruno. |
| [01-health.bru](01-health.bru) | `GET /health` | Проверка доступности API и базы данных. |
| [02-register.bru](02-register.bru) | `POST /auth/register` | Регистрация тестового пользователя. |
| [03-create-operator.bru](03-create-operator.bru) | `POST /auth/operators` | Создание оператора с расширенными правами. |
| [04-login.bru](04-login.bru) | `POST /auth/login` | Вход оператора и сохранение JWT-токена в окружение. |
| [05-me.bru](05-me.bru) | `GET /auth/me` | Получение профиля авторизованного пользователя. |
| [06-refresh.bru](06-refresh.bru) | `POST /auth/refresh` | Обновление пары JWT-токенов по refresh token. |
| [07-capabilities.bru](07-capabilities.bru) | `GET /capabilities` | Получение перечня поддерживаемых профилей. |
| [08-data-status.bru](08-data-status.bru) | `GET /data-status` | Проверка статуса свежести данных и ревизий. |
| [09-network.bru](09-network.bru) | `GET /network` | Снимок топологии сети. |
| [10-routes.bru](10-routes.bru) | `GET /routes` | Список обслуживаемых трамвайных маршрутов. |
| [11-route.bru](11-route.bru) | `GET /routes/{id}` | Полная топология маршрута с остановками и геометрией. |
| [12-stops.bru](12-stops.bru) | `GET /stops` | Справочник остановок сети. |
| [13-observations.bru](13-observations.bru) | `GET /observations` | Исторические фактические наблюдения пассажиропотока. |
| [14-create-forecast.bru](14-create-forecast.bru) | `POST /forecast-runs` | Постановка асинхронного задания прогноза. |
| [15-list-forecasts.bru](15-list-forecasts.bru) | `GET /forecast-runs` | Получение списка расчетов прогнозов. |
| [16-get-forecast.bru](16-get-forecast.bru) | `GET /forecast-runs/{id}` | Опрос статуса выполнения расчета воркером. |
| [17-forecast-points.bru](17-forecast-points.bru) | `GET /forecast-runs/{id}/points` | Получение точек временного ряда прогноза. |
| [18-forecast-map.bru](18-forecast-map.bru) | `GET /forecast-runs/{id}/map` | Получение GeoJSON слоя прогнозируемой загрузки. |
| [19-list-evaluations.bru](19-list-evaluations.bru) | `GET /evaluations` | Список исторических отчетов валидации. |
| [20-get-evaluation.bru](20-get-evaluation.bru) | `GET /evaluations/{id}` | Детальный отчет оценки качества. |
| [21-evaluation-points.bru](21-evaluation-points.bru) | `GET /evaluations/{id}/points` | Точки факт vs прогноз на истории. |
| [22-logout.bru](22-logout.bru) | `POST /auth/logout` | Выход пользователя и отзыв токена. |
| [23-list-models.bru](23-list-models.bru) | `GET /models` | Получение реестра ML-моделей. |
| [24-get-model.bru](24-get-model.bru) | `GET /models/{id}` | Получение паспорта конкретной модели. |

## Подпапки

- [environments](environments/README.md).
