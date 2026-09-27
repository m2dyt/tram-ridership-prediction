0. Сначала положить датасет в папку dataset/ в корне проекта (без него импорт данных и обучение не запустятся):
- Распаковать архив конкурса dataset.zip прямо в dataset/, без вложенной папки с именем архива.
- Обязательно должны появиться: dataset/labels/labels_day_train.csv, dataset/labels/labels_day_test.csv, dataset/test_submission.csv.
- Справочники (dataset/spravochniki/) и сырые dataset/train.csv, dataset/test.csv можно положить рядом; сырые файлы в базу не загружаются.
- Папка dataset/ исключена из Git, кроме dataset/PROJECT_DATA.md — там описана полная структура.
- Затем полный запуск со всеми миграциями, импортом и обучением: sh scripts/start-stack.sh

1. Запуск через Docker Compose одной командой:
docker compose up -d

2. Запуск без Docker (локально):
# Backend (FastAPI + Worker):
tram migrate
tram serve --port 8000
tram worker

# Frontend (React + Vite + Leaflet карта):
cd frontend && npm ci && npm run dev

3. Точки входа API и веб-интерфейса:
- Веб-интерфейс (Frontend): http://127.0.0.1:5173 (или http://127.0.0.1:8000/ при прод-сборке)
- Интерактивная документация Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI спецификация: http://127.0.0.1:8000/openapi.yaml
- Health-check: GET http://127.0.0.1:8000/api/v1/health
- Создание прогноза: POST http://127.0.0.1:8000/api/v1/forecast-runs
- Получение точек прогноза: GET http://127.0.0.1:8000/api/v1/forecast-runs/{run_id}/points
- GeoJSON сети и остановок: GET http://127.0.0.1:8000/api/v1/context/snapshots/{id}/geojson
- Симуляция рейса и наполненности вагона: POST http://127.0.0.1:8000/api/v1/occupancy/trips

4. Вход оператора (фиксированная учётная запись, одинаковая у всех установок):
- Логин: operator
- Пароль: Tram-Operator-2025
- Роль: operator (запуск прогнозов и другие команды записи)
- Учётную запись создаёт миграция 0006_shared_operator (tram migrate или запуск через Docker), а scripts/bootstrap-operator.py при каждом sh scripts/start-stack.sh восстанавливает её, если её удалили, отключили или сменили пароль.
- Только для локального стенда: API в Docker слушает 127.0.0.1. Перед публичным развёртыванием смените пароль или удалите учётную запись (см. docs/DOCKER_STACK.md).