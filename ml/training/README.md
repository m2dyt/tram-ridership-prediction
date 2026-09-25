# ml/training — подготовка признаков, обучение и оценка моделей

Внешний слой для проведения машинного обучения (в отличие от `ml/src/tram_ml`, который остаётся чистым ядром без тяжелых внешних библиотек).

## Состав модулей

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Инициализация пакета обучения. |
| [prepare.py](prepare.py) | Извлечение матрицы признаков (сезонные лаги, скользящие средние, гео-контекст) без заглядывания в будущее (*leakage-free*). |
| [train.py](train.py) | Обучение моделей (Ridge, HistGradientBoosting) строго на периоде `train_start` .. `validation_start` и сохранение паспорта модели. |
| [evaluate.py](evaluate.py) | Сравнение обученной модели с сезонным бейзлайном на валидационной и тестовой выборках (MAE, WAPE). |

## Пример запуска

```powershell
# 1. Извлечение признаков
python -m ml.training.prepare --bundle data/metro/moscow-20260922 --output data/training/metro-v1

# 2. Обучение модели
python -m ml.training.train --features data/training/metro-v1 --config ml/experiments/metro_ridge_v1.json --output models/metro_ridge_v1

# 3. Оценка качества и бенчмарк против бейзлайна
python -m ml.training.evaluate --model models/metro_ridge_v1 --features data/training/metro-v1 --baseline data/metro-evaluation/seasonal-20260922
```
