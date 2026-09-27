# models — версии обученных моделей (Model Registry)

Каталог содержит версионированные, неизменяемые бандлы обученных моделей для прогнозирования пассажиропотока трамваев.

---

## 1. Архитектура бандла модели `models/tram/<version>/`

Каждый бандл модели изолирован и защищён контрольной суммой:

```text
models/tram/
├── <version>/
│   ├── estimator.joblib       # Сериализованная модель (алгоритм + исторические профили)
│   ├── manifest.json          # SHA-256 артефакта, git commit, дата создания, список файлов
│   ├── features.json          # Спецификация признаков и категориальных колонок
│   ├── config.json            # Гиперпараметры, режим residual learning, горизонт
│   ├── metrics.json           # Метрики валидации (Overall WAPE, WAPE-score, MAE, помаршрутный срез)
│   └── model-card.md          # Паспорт модели (описание, применимость, ограничения)
├── active_version.txt         # Указатель на текущую активную версию модели
└── README.md
```

---

## 2. Загрузка и проверка целостности в Python

```python
from ml.training.tram.bundle import load_model_bundle, get_active_version

# Загрузка активной версии
active_ver = get_active_version()
bundle = load_model_bundle(active_ver)

# Инференс на любых новых данных (сетка с датой, часом, маршрутом)
# Автоматически добавляет календарные фичи и профили:
predictions = bundle.predict(grid_df)
```

При загрузке автоматически проверяется контрольная сумма `SHA-256` файла `estimator.joblib`. При несовпадении хеша выбрасывается `ChecksumMismatchError`.

---

## 3. Выпуск новой версии модели через CLI

```powershell
# Обучение и экспорт бандла версии v1 с установкой её активной:
python ml/training/train_tram.py --model histgradient --export-bundle v1 --set-active

# Экспорт с перезаписью существующей версии (если требуется):
python ml/training/train_tram.py --model baseline --export-bundle baseline_v1 --overwrite --set-active
```
