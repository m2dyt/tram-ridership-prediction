export const number = (value, digits = 1) =>
  value == null
    ? "Нет данных"
    : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(
        value,
      );
export const date = (value) =>
  value
    ? new Intl.DateTimeFormat("ru-RU", {
        timeZone: "Europe/Moscow",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "—";
export const localInput = (value) =>
  value
    ? new Date(new Date(value).getTime() + 3 * 3600000)
        .toISOString()
        .slice(0, 16)
    : "";
export const moscowTime = (value) => value + ":00+03:00";
export const seriesKey = (point) => JSON.stringify(point.spatial);
export const unitName = (metric) =>
  ({
    validations: "валидаций",
    boardings: "пассажиров",
    occupancy: "пассажиров",
    occupancy_ratio: "доля вместимости",
  })[metric] || metric;
export const horizonName = (horizon) =>
  ({ day: "Сутки", month: "Месяц", year: "Год" })[horizon] || horizon;
export const statusName = (status) =>
  ({
    queued: "В очереди",
    running: "Вычисляется",
    succeeded: "Готово",
    failed: "Ошибка",
    complete: "Рассчитан",
    unavailable: "Недоступен",
    active: "В пути",
    completed: "Завершён",
  })[status] || status;
export function csvCell(value) {
  let text = value == null ? "" : String(value);
  if (/^[=+@\-\t\r]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
export function exportCsv(points) {
  const keys = [
    "interval_start",
    "interval_end",
    "value",
    "actual",
    "model",
    "missing_reason",
  ];
  return (
    "\uFEFF" +
    [
      keys.join(","),
      ...points.map((p) => keys.map((k) => csvCell(p[k])).join(",")),
    ].join("\r\n")
  );
}
export function chartSegments(points, field = "value") {
  const segments = [];
  let current = [];
  points.forEach((p, i) => {
    if (p[field] == null) {
      if (current.length) segments.push(current);
      current = [];
    } else current.push([i, p[field]]);
  });
  if (current.length) segments.push(current);
  return segments;
}
