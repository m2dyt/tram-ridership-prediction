# Frontend

React 19 на JavaScript/JSX, Vite 8, Leaflet/OSM. Node 22.12+ в ветке 22 либо 24+.

```powershell
npm.cmd ci
npm.cmd run dev
```

API-прокси по умолчанию: 127.0.0.1:8000; интерфейс: 127.0.0.1:5173. `npm run build` создаёт dist, который раздаёт FastAPI при следующем запуске. `npm run test`, `npm run format:check` — проверки. Ключ API вводится в интерфейсе и хранится только в памяти. Не добавлять секреты поставщиков в VITE_* или исходники. OSM-тайлы требуют атрибуции и доступа к сети; bulk/offline скачивание не выполняется.

## Файлы

| Файл | Назначение |
|---|---|
| [index.html](index.html) | HTML-точка входа приложения, язык, viewport, заголовок. |
| [package-lock.json](package-lock.json) | Точные транзитивные npm-зависимости и integrity для воспроизводимого npm ci. |
| [package.json](package.json) | Точные версии React/Leaflet/Vite/Prettier и команды разработки, сборки, тестов, форматирования. |
| [vite.config.js](vite.config.js) | Vite dev/proxy API+Swagger, порты, сборка и preview. |

## Подпапки

- [src](src/README.md).
- [tests](tests/README.md).
