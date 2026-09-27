# ML Infrastructure Adapters

Адаптеры инфраструктурного слоя для интеграции обученных моделей машинного обучения с ядром бэкенда (`tram.application.ports.Predictor`).

## Файлы

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Маркер Python-пакета инфраструктурного слоя ML. |
| [artifact_predictor.py](artifact_predictor.py) | Реализация порта `Predictor` (`ArtifactPredictor`) для метода `tram_bundle`: загружает `TramModelBundle` с проверкой SHA-256. `from_version` — строгая загрузка для worker без отката; `from_active_version` с `fallback` оставлен для бенчмарка. |
| [model_catalog.py](model_catalog.py) | `FileModelCatalog`: описание настроенного бандла (`TRAM_MODEL_VERSION` или `active_version.txt`) по метаданным без десериализации — статус, `ModelReference` для запуска, маршруты, причина недействительности; кэш по изменению файлов. |
| [model_registry.py](model_registry.py) | Проверка версии, состава, JSON и SHA-256 бандла для HTTP-реестра без десериализации `estimator.joblib`. |
