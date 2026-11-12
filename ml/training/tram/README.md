# Модули обучения и инференса трамвайной модели (ml/training/tram)

Декомпозированная модульная архитектура пайплайна прогнозирования пассажиропотока трамвайных маршрутов Москвы.

---

## 1. Структура модулей

| Файл | Назначение |
|---|---|
| [__init__.py](__init__.py) | Маркер пакета `ml.training.tram`. |
| [adaptive.py](adaptive.py) | Рабочая модель сервиса (рецепт `adaptive_v2`): база из свежих 4 недель, модель поправки на остатках, выбор по отложенным неделям, диапазон прогноза. Одни и те же функции используются при обучении и на сервере. |
| [calendar.py](calendar.py) | Признаки производственного календаря РФ: праздники, сокращённые дни, рабочие выходные на 2024–2027 годы. |
| [production_calendar_ru.csv](production_calendar_ru.csv) | Таблица производственного календаря по дням (выходной, сокращённый); создаётся `scripts/fetch_production_calendar.py`. |
| [production_calendar_ru.meta.json](production_calendar_ru.meta.json) | Источник календаря, дата загрузки и SHA-256. |
| [service.py](service.py) | Обучение и выгрузка рабочей модели: версия `<version>` (на всей истории) и `<version>-check` (до отложенных недель, для честной проверки). |
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
# Рабочая модель сервиса (её обучает scripts/train-model.sh на стенде):
python -m ml.training.tram.service --data-dir dataset --version service-test --set-active

# Обучение CatBoost с экспортом бандла и генерацией submission.csv:
python -m ml.training.tram.cli --model catboost --iterations 2000 --export-bundle catboost-v1 --set-active

# Обучение быстрой CPU-модели HistGradientBoosting:
python -m ml.training.tram.cli --model histgradient --export-bundle hgb-v1

# Только валидация на отложенном периоде (сентябрь-октябрь 2025):
python -m ml.training.tram.cli --model catboost --eval-only

# Валидация файла предсказаний по соревновательному регламенту:
python scripts/validate_submission.py ml/predictions/submission.csv
```
