# ML Infrastructure Adapters

Адаптеры инфраструктурного слоя для интеграции обученных моделей машинного обучения с ядром бэкенда (`tram.application.ports.Predictor`).

## Файлы

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Маркер Python-пакета инфраструктурного слоя ML. |
| [artifact_predictor.py](artifact_predictor.py) | Реализация порта `Predictor` (`ArtifactPredictor`), подключающая версионированные бандлы моделей (`TramModelBundle`) к API и воркеру с SHA-256 валидацией и откатом на `SeasonalNaive`. |
