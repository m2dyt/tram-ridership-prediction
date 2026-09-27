ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm
ARG NODE_IMAGE=node:22.23.2-alpine
FROM ${NODE_IMAGE} AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
COPY frontend/public ./public
RUN npm run build

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml /app/
COPY backend/src /app/backend/src
COPY ml/src /app/ml/src
COPY ml/training /app/ml/training
COPY scripts /app/scripts
COPY frontend/public /app/frontend/public
RUN python -m pip install --no-cache-dir --timeout 20 --retries 1 . && useradd --uid 10001 --create-home tram \
    && mkdir -p /app/models/tram /app/ml/predictions \
    && chown -R tram:tram /app/models /app/ml/predictions
COPY alembic.ini openapi.yaml /app/
COPY backend/migrations /app/backend/migrations
COPY --from=frontend /frontend/dist /app/frontend/dist
USER tram
EXPOSE 8000
CMD ["python", "-m", "tram.cli", "serve", "--host", "0.0.0.0"]
