# ML: подготовка данных, эксперименты и прогноз

В `ml/` сейчас живут две разные задачи, поэтому результаты и данные нельзя смешивать.

| Задача | Реализация | Гранулярность/выход | Текущий статус |
|---|---|---|---|
| Хакатон трамваев | [`training/train_tram.py`](training/train_tram.py), [`training/README_TRAM_TRAINING.md`](training/README_TRAM_TRAINING.md) | route × date × hour; CSV `ml/predictions/submission.csv` | Код генерации прогноза существует. Нужно перепроверить входные файлы, правила нулей, validation, метрику и происхождение итогового файла. Он не подключён к API. |
| Эксперимент метро | [`training/prepare.py`](training/prepare.py), [`train.py`](training/train.py), [`evaluate.py`](training/evaluate.py) | станция/линия × квартал | Изолированный pipeline для данных 624/62743; это не почасовой target трамвая. Проверь известные mapping/category вопросы до использования его метрик. |
| ML основы и backend port | [`src/tram_ml`](src/tram_ml/README.md) | Domain-neutral protocol/models | `SeasonalNaive` используется в composition текущего worker; `Predictor` protocol определён в backend. Обученная модель пока не подключена в текущий HTTP prediction path. |

## Порядок работы над моделью трамвая

Сначала проверить конкурсный архив и словарь полей, затем ключи/пропуски/нули и sample, воспроизвести WAPE-score и базу. После этого зафиксировать временные splits, оценить существующие поправки и лишь затем добавлять погодные и календарные признаки. События и traffic использовать только после проверки исторического покрытия и доступности данных на дату прогноза. Все детали, критерии ревью и список задач находятся в [плане готовности](../docs/HACKATHON_READINESS_PLAN.md) и [очереди задач](../docs/ML_BACKEND_TASKS.md).

## Где что искать

- Исходные выгрузки и provenance: [`sources/`](../sources/README.md); нормализованные данные и отчёты: [`data/`](../data/README.md). Эти каталоги в основном исключены из Git.
- Конфигурации экспериментов: [`experiments/`](experiments/README.md).
- Модели и паспорта: [`models/`](../models/README.md).
- Сформированный конкурсный CSV: [`predictions/`](predictions/README.md); сверяй его с test keys и платформенным результатом.
- Команды доступной подготовки/оценки: [docs/OPERATIONS.md](../docs/OPERATIONS.md) и [docs/METRO_PIPELINE.md](../docs/METRO_PIPELINE.md).
- Актуальное состояние по областям: [docs/STATUS.md](../docs/STATUS.md).

Не использовать высокоуровневые claims из старого `README_TRAM_TRAINING.md` до пересчёта по зафиксированным входам и понятному validation. В частности, процент score — не свойство скрипта; он всегда связан с конкретными данными, временной схемой и версией кода.
