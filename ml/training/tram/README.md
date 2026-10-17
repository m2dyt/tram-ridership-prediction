# Модули обучения и инференса трамвайной модели (ml/training/tram)

Декомпозированная модульная архитектура пайплайна прогнозирования пассажиропотока трамвайных маршрутов Москвы.

---

## 1. Структура модулей

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Маркер пакета `ml.training.tram`. |
| [baseline.py](baseline.py) | Реализация `SeasonalBaseline` (сезонный расчет медианных и средних профилей). |
| [bundle.py](bundle.py) | Экспорт и сериализация бандлов моделей в `models/tram/<version>/` с расчетом хэшей SHA-256 и манифестом. |
| [cli.py](cli.py) | Консольный интерфейс обучения, валидации и экспорта (`--model`, `--iterations`, `--export-bundle`, `--set-active`). |
| [evaluation.py](evaluation.py) | Out-of-Time кросс-валидация и расчет метрики WAPE-score по маршрутам. |
| [features.py](features.py) | Конвейер генерации признаков (календарные, погодные, обособленность путей `tramlanes.geojson`, лаги). |
| [models.py](models.py) | Обертки над моделями `CatBoostRegressor` и `HistGradientBoostingRegressor`. |
| [submission.py](submission.py) | Формирование конкурсных CSV-файлов предсказаний с жестким занулением маршрута 5. |

---

## 2. Команды запуска

```bash
# Обучение CatBoost с экспортом бандла и генерацией submission.csv:
python -m ml.training.tram.cli --model catboost --iterations 2000 --export-bundle catboost-v1 --set-active

# Обучение быстрой CPU-модели HistGradientBoosting:
python -m ml.training.tram.cli --model histgradient --export-bundle hgb-v1

# Только валидация на отложенном периоде (сентябрь-октябрь 2025):
python -m ml.training.tram.cli --model catboost --eval-only

# Валидация файла предсказаний по соревновательному регламенту:
python scripts/validate_submission.py ml/predictions/submission.csv
```
