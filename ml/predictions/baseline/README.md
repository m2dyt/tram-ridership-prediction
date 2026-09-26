# Замороженный эталон прогнозов (Baseline)

В этой папке хранятся неизменяемые эталонные копии лучшего базового сабмита.

## Файлы

| Файл | Назначение |
|---|---|
| [submission_best_baseline.csv](submission_best_baseline.csv) | Зафиксированная копия сабмита (хронологический порядок: route, date, hour). |
| [submission_best_baseline_aligned.csv](submission_best_baseline_aligned.csv) | Идентичная по содержимому копия, выровненная 1-в-1 по порядку строк официального `dataset/test_submission.csv`. |
| [submission_best_baseline.meta.json](submission_best_baseline.meta.json) | Паспорт эталона: SHA-256 суммы, метрики локальной валидации (WAPE 0.0947, WAPE-score 0.9053, MAE 82.50). |
