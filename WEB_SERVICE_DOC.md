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