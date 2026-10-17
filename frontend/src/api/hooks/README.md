# frontend/src/api/hooks — React-хуки для API

Модульные хуки для взаимодействия с бэкендом:

---

## Файлы

| Файл                                     | Назначение                                                           |
| ---------------------------------------- | -------------------------------------------------------------------- |
| [\_utils.js](_utils.js)                  | Вспомогательные утилиты для хуков (обработка состояний, ключи кэша). |
| [useAuth.js](useAuth.js)                 | Хук авторизации: логин, логаут, текущий пользователь (`/auth/me`).   |
| [useCatalogs.js](useCatalogs.js)         | Справочники маршрутов и остановок.                                   |
| [useContext.js](useContext.js)           | Снимки внешнего контекста (погода, события).                         |
| [useEvaluations.js](useEvaluations.js)   | Исторические отчеты и валидация.                                     |
| [useForecasts.js](useForecasts.js)       | Создание расчетов, опрос статуса воркера и получение точек прогноза. |
| [useModels.js](useModels.js)             | Реестр моделей, переключение активной версии.                        |
| [useObservations.js](useObservations.js) | Загрузка исторических наблюдений пассажиропотока.                    |
| [useOccupancy.js](useOccupancy.js)       | Симуляция рейсов и баланс пассажиров в вагоне.                       |
| [useSystem.js](useSystem.js)             | Системные проверки health, capabilities и data-status.               |
