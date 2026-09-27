// Forecast aggregation helpers: grid-aligned period inputs (Moscow is fixed UTC+3)
// and groupings the backend accepts for a profile's resolution and spatial level.

const MSK = 3 * 3600000;
const STEP = { hour: 3600000, day: 86400000 };
const GRAIN = ["hour", "day", "month"];

export const inputType = (resolution) =>
  ({ hour: "datetime-local", day: "date", month: "month" })[resolution];

const moscowIso = (ms) =>
  new Date(ms + MSK).toISOString().slice(0, 19) + "+03:00";

const shiftMonth = (value, months) => {
  const [year, month] = value.split("-").map(Number);
  const index = year * 12 + month - 1 + months;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
};

// ISO instant -> value of the period input (Moscow wall time at the profile grain).
export function toInput(iso, resolution) {
  if (!iso) return "";
  const local = new Date(new Date(iso).getTime() + MSK).toISOString();
  if (resolution === "month") return local.slice(0, 7);
  if (resolution === "day") return local.slice(0, 10);
  return local.slice(0, 13) + ":00";
}

// Period input -> inclusive start of that bucket as an ISO instant with offset.
export function fromInput(value, resolution) {
  if (!value) return null;
  if (resolution === "month") return `${value.slice(0, 7)}-01T00:00:00+03:00`;
  if (resolution === "day") return `${value.slice(0, 10)}T00:00:00+03:00`;
  return `${value.slice(0, 13)}:00:00+03:00`;
}

// The user picks the last included bucket; the API needs the exclusive end.
export function endFromInput(value, resolution) {
  const start = fromInput(value, resolution);
  if (!start) return null;
  if (resolution === "month")
    return `${shiftMonth(value.slice(0, 7), 1)}-01T00:00:00+03:00`;
  return moscowIso(new Date(start).getTime() + STEP[resolution]);
}

// Exclusive end ISO -> input value of the last included bucket.
export function lastInput(endIso, resolution) {
  if (!endIso) return "";
  if (resolution === "month") return shiftMonth(toInput(endIso, "month"), -1);
  return toInput(
    new Date(new Date(endIso).getTime() - STEP[resolution]).toISOString(),
    resolution,
  );
}

export const levelSupports = (level) => ({
  direction: ["route_direction", "stop", "segment"].includes(level),
  stop: level === "stop",
  segment: level === "segment",
});

export function groupOptions(resolution, level) {
  const labels = {
    hour: "По часам",
    day: "По дням",
    month: "По месяцам",
  };
  const supports = levelSupports(level);
  return [
    { value: "none", label: "Только итог" },
    ...GRAIN.slice(GRAIN.indexOf(resolution)).map((grain) => ({
      value: grain,
      label: labels[grain],
    })),
    ...(supports.direction
      ? [{ value: "direction", label: "По направлениям" }]
      : []),
    ...(supports.stop ? [{ value: "stop", label: "По остановкам" }] : []),
    ...(supports.segment ? [{ value: "segment", label: "По участкам" }] : []),
  ];
}

export const perInterval = (resolution) =>
  ({ hour: "час", day: "день", month: "месяц" })[resolution] || "интервал";

export const isTimeGroup = (groupBy) => GRAIN.includes(groupBy);

// Human label of a spatial group using the route catalogue.
export function spatialLabel(group, route) {
  const stops = Object.fromEntries(
    (route?.stops || []).map((s) => [s.id, s.name]),
  );
  const directions = route?.directions || [];
  const direction = directions.find((d) => d.id === group.direction_id);
  if (group.segment_id) {
    const segment = directions
      .flatMap((d) => d.segments || [])
      .find((s) => s.id === group.segment_id);
    return segment
      ? `${stops[segment.from_stop_id] || segment.from_stop_id} → ${stops[segment.to_stop_id] || segment.to_stop_id}`
      : group.segment_id;
  }
  if (group.stop_id) {
    const name = stops[group.stop_id] || group.stop_id;
    return group.stop_sequence ? `${group.stop_sequence}. ${name}` : name;
  }
  if (group.direction_id) return direction?.name || group.direction_id;
  return route?.route?.number
    ? `Маршрут ${route.route.number}`
    : group.route_id || "—";
}
