# Модули обучения и инференса трамвайной модели (ml/training/tram)

Декомпозированная модульная архитектура пайплайна прогнозирования пассажиропотока трамвайных маршрутов Москвы.

1. Код обучения, валидации и экспорта:
- Пайплайн обучения: ml/training/tram/ (features.py, baseline.py, models.py, evaluation.py, bundle.py, cli.py)
- Единый CLI запуска: ml/training/train_tram.py
- Артефакты и бандлы моделей: models/tram/ (веса, профили, schema признаков, SHA-256 манифест)
- Готовые предсказания: ml/predictions/submission.csv и кандидаты в ml/predictions/candidates/

2. Инструкция запуска обучения и инференса:
# Локальное окружение
pip install -r requirements.txt -e .

# Обучение модели с автоматическим экспортом бандла и генерацией submission.csv:
python -m ml.training.tram.cli --model catboost --iterations 2000 --export-bundle catboost-v1 --set-active

# Только быстрая валидация (Sep-Oct 2025 hold-out):
python -m ml.training.tram.cli --model catboost --eval-only

# Валидация файла предсказаний по формату организаторов:
python scripts/validate_submission.py ml/predictions/submission.csv
