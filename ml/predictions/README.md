# ml/predictions — выходные прогнозы и конкурсные сабмиты

Данный каталог содержит эталонные и кандидатные файлы прогнозов для соревнования по предсказанию почасового пассажиропотока трамваев (ноябрь–декабрь 2025).

---

## 1. Структура каталогов

```text
ml/predictions/
├── baseline/
│   ├── submission_best_baseline.csv           # Зафиксированный лучший сабмит (хронологический порядок)
│   ├── submission_best_baseline_aligned.csv   # Зафиксированный лучший сабмит (1:1 порядок official test_submission.csv)
│   └── submission_best_baseline.meta.json     # Паспорт эталона: SHA-256, WAPE-score, число строк, валидация
├── candidates/
│   └── .gitkeep                               # Сюда сохраняются черновые прогоны новых моделей
└── README.md
```

---

## 2. Зафиксированный эталон (Baseline)

* **Метрика валидации (Sep-Oct 2025):**
  * `Overall WAPE`: **0.0947 (9.47%)**
  * `Overall WAPE-score`: **0.9053** (целевой бенчмарк хакатона $> 0.88$ превзойдён)
  * `Overall MAE`: 82.50
  * `Всего предсказано пассажиров (Nov-Dec)`: 12 712 823
* **SHA-256 контрольные суммы:**
  * `submission_best_baseline.csv`: `272b5ce7aa72c5ff2bdd13d98534ffa493567aef66663fb61ce679daffb875fd`
  * `submission_best_baseline_aligned.csv`: `5d332d4907efaca0dc6b07af7973f06afd6eddba2bbf8ca99929827d683356d8`

---

## 3. Валидация сабмитов (`scripts/validate_submission.py`)

Перед отправкой файла на платформу запустите проверку:

```bash
# Базовая валидация структуры, пропусков, неотрицательности и маршрута 5:
python scripts/validate_submission.py ml/predictions/baseline/submission_best_baseline_aligned.csv

# Валидация с проверкой строгого порядка строк по официальному test_submission.csv:
python scripts/validate_submission.py ml/predictions/candidates/my_new_sub.csv --sample dataset/test_submission.csv

# Валидация со сравнением отклонений относительно базового эталона (WAPE / MAE divergence):
python scripts/validate_submission.py ml/predictions/candidates/my_new_sub.csv --baseline ml/predictions/baseline/submission_best_baseline_aligned.csv

# Автоматическое приведение порядка строк кандидата к каноническому образцу sample:
python scripts/validate_submission.py ml/predictions/candidates/my_new_sub.csv --sample dataset/test_submission.csv --sort-to ml/predictions/candidates/my_new_sub_aligned.csv
```

---

## 4. Правила генерации кандидатов

1. Новые эксперименты **запрещено** сохранять напрямую в `ml/predictions/submission.csv`.
2. Результаты тренировок сохраняются в `ml/predictions/candidates/submission_<model_name>_<timestamp>.csv`.
3. Замена основного сабмита производится только после того, как:
   - `python scripts/validate_submission.py` прошёл без ошибок;
   - локальный `WAPE-score` кандидата на валидации строго выше текущего эталона (`> 0.9053`).
