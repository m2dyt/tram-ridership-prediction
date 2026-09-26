# Конфигурации экспериментов обучения (ML Experiments)

В этой папке хранятся декларативные JSON-спецификации экспериментов обучения моделей пассажиропотока трамвайных маршрутов.

## Файлы

| Файл | Назначение |
|---|---|
| [tram_baseline_v1.json](tram_baseline_v1.json) | Конфигурация чистого исторического сезонного baseline (исторические медианные профили). |
| [tram_histgradient_v1.json](tram_histgradient_v1.json) | Конфигурация модели HistGradientBoosting (scikit-learn) с обучением на остатках (residual learning). |
| [tram_catboost_v1.json](tram_catboost_v1.json) | Конфигурация специализированных per-route моделей CatBoostRegressor с ранней остановкой и оптимизацией MAE. |
| [metro_gbdt_v1.json](metro_gbdt_v1.json) | Конфигурация отдельного квартального эксперимента модели метро на базе GBDT. |
| [metro_ridge_v1.json](metro_ridge_v1.json) | Конфигурация линейного baseline для квартального эксперимента модели метро. |

