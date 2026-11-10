import { forecastModelLabel } from "./forecast.js";

export function evaluationModelLabel(model) {
  if (!model) return "Модель не указана";
  if (model.method === "seasonal_naive_v1") return "Сезонная базовая модель";
  if (model.method === "tram_bundle") return forecastModelLabel(model);
  return `${model.is_baseline ? "Базовая модель" : "Модель"}${model.method ? ` · ${model.method}` : ""}`;
}

export function evaluationStatusLabel(status) {
  return (
    {
      complete: "Проверка завершена",
      insufficient_history: "Недостаточно истории для проверки",
      unavailable: "Проверка недоступна",
    }[status] || "Статус проверки неизвестен"
  );
}
