import { date, localInput, moscowTime } from "./format.js";

export function forecastIssue({
  profile,
  role,
  asOf,
  start,
  now = new Date(),
}) {
  if (!role) return "Проверяем права доступа к расчёту.";
  if (role !== "operator")
    return "Запуск доступен пользователю с ролью оператора.";
  if (profile?.availability !== "available")
    return (
      profile?.unavailable_reason ||
      "Прогноз для выбранного профиля недоступен."
    );
  if (!asOf || !start) return "Укажите дату начала и дату доступных данных.";

  const inRange = (value, min, max) =>
    min && max && value >= localInput(min) && value <= localInput(max);
  if (
    !inRange(asOf, profile.allowed_as_of_start, profile.allowed_as_of_end) ||
    !inRange(start, profile.forecast_start_min, profile.forecast_start_max)
  )
    return "Выберите даты в пределах допустимого диапазона.";
  if (Date.parse(moscowTime(asOf)) > now.getTime() || asOf > start)
    return "Дата доступных данных не может быть в будущем или позже начала прогноза.";
  if (
    ["local_midnight", "month_start"].includes(profile.start_alignment) &&
    !start.endsWith("T00:00")
  )
    return "Начало прогноза должно приходиться на полночь по московскому времени.";
  if (profile.start_alignment === "month_start" && start.slice(8, 10) !== "01")
    return "Годовой прогноз начинается первого числа месяца.";
  return null;
}

export function forecastModelLabel(model) {
  if (!model?.method) return "Метод не указан";
  const method =
    model.method === "tram_bundle"
      ? model.is_baseline
        ? "Базовая модель по сезонному профилю"
        : "Обученная модель"
      : model.method === "seasonal_naive_v1"
        ? "Сезонная базовая модель"
        : model.method;
  return model.version ? `${method} · ${model.version}` : method;
}
const FORECAST_MESSAGES = {
  "Synthetic demonstration data; not real ridership or measured model accuracy":
    "Синтетические демонстрационные данные не отражают реальный пассажиропоток или измеренную точность модели.",
  "Stop values are an estimated split of the route total":
    "Значения по остановкам получены через оценочное распределение общего потока маршрута.",
  "Seasonal baseline; no model training was performed":
    "Используется сезонный базовый метод; модель не обучалась.",
  "Baseline only; no trained model or regression":
    "В отчёте проверен базовый метод; обученная модель и регрессия не использовались.",
  "model equals seasonal_naive; no training was performed":
    "Проверяемая модель совпадает с сезонным базовым методом; обучение не проводилось.",
  "Overlapping folds count their forecasts separately":
    "Прогнозы пересекающихся периодов проверки учитываются отдельно.",
  "External context is not used by seasonal baseline":
    "Сезонный базовый метод не использует внешние данные.",
  "Both methods are scored on the same intervals only":
    "Обе модели оцениваются только на одних и тех же часах.",
};

export function explainForecastText(value) {
  if (Object.hasOwn(FORECAST_MESSAGES, value)) return FORECAST_MESSAGES[value];
  const seasonalBundle =
    /^Model bundle (.+) is a seasonal-profile baseline; no model was fitted$/.exec(
      value,
    );
  if (seasonalBundle)
    return `Пакет модели ${seasonalBundle[1]} использует сезонный базовый метод; обучение не проводилось.`;
  const checked =
    /^Trained model (.+) checked on folds after its training history; the seasonal baseline is shown on the same intervals$/.exec(
      value,
    );
  return checked
    ? `Проверена обученная модель ${checked[1]} на днях после конца её обучающей истории; сезонная база показана на тех же часах.`
    : value;
}

export function forecastDateRange(min, max) {
  if (!min && !max) return "не указан";
  if (!min || !max) return date(min || max);
  return Date.parse(min) === Date.parse(max)
    ? date(min)
    : `${date(min)} — ${date(max)}`;
}
export function forecastCoverageLabel({ loading, error, points }) {
  if (loading) return "Загрузка…";
  if (error || !points?.length) return "Нет данных";
  return `${points.filter((point) => point.value != null).length} / ${points.length}`;
}
