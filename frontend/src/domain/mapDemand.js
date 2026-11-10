export const HOUR = 3600000;
const DAY = 24 * HOUR;
const MOSCOW_OFFSET = 3 * HOUR;
export const MAX_DEMAND_DAYS = 7;

export const demandBands = {
  low: { label: "Ниже среднего", color: "#238776" },
  typical: { label: "Около среднего", color: "#2268ad" },
  high: { label: "Повышенная", color: "#b66116" },
  peak: { label: "Пиковая", color: "#bb3651" },
  unknown: { label: "Нет оценки", color: "#788795" },
};

export const localDay = (instant) =>
  new Date(instant + MOSCOW_OFFSET).toISOString().slice(0, 10);

export const dayStart = (day) => `${day}T00:00:00+03:00`;

function eligibleProfiles(caps) {
  return caps.forecast_profiles.filter(
    (profile) =>
      profile.availability === "available" &&
      profile.horizon === "day" &&
      profile.resolution === "hour" &&
      profile.metric === "validations" &&
      profile.aggregation_method === "sum" &&
      ["route", "stop"].includes(profile.spatial_level) &&
      profile.forecast_start_min &&
      profile.forecast_start_max,
  );
}

export function demandDates(caps) {
  const profiles = eligibleProfiles(caps);
  if (!profiles.length) return null;
  const min = Math.min(
    ...profiles.map((p) => Date.parse(p.forecast_start_min)),
  );
  const max = Math.max(
    ...profiles.map((p) => Date.parse(p.forecast_start_max)),
  );
  return {
    min: localDay(min),
    max: localDay(max),
    initial: localDay(
      Math.max(
        min,
        Math.min(max, Date.parse(dayStart(localDay(Date.now()))) + DAY),
      ),
    ),
  };
}

export function demandHours(from, to) {
  const first = Date.parse(dayStart(from));
  const last = Date.parse(dayStart(to));
  const count = (last - first) / HOUR + 24;
  if (!Number.isInteger(count) || count < 24 || count > MAX_DEMAND_DAYS * 24)
    return [];
  return Array.from({ length: count }, (_, index) => first + index * HOUR);
}

export function demandPlan(caps, routes, from, to, now = Date.now()) {
  const hours = demandHours(from, to);
  const profiles = eligibleProfiles(caps);
  const limit = caps.max_routes_per_run || 100;
  const plan = [];
  for (let index = 0; index < hours.length; index += 24) {
    const start = hours[index];
    const day = localDay(start);
    const nextDay = localDay(start + DAY);
    const valid = new Set(
      routes
        .filter(
          ({ route }) =>
            route.valid_from <= day &&
            (!route.valid_to || route.valid_to >= nextDay),
        )
        .map(({ route }) => route.id),
    );
    const assigned = { route: new Set(), stop: new Set() };
    for (const profile of profiles) {
      if (
        start < Date.parse(profile.forecast_start_min) ||
        start > Date.parse(profile.forecast_start_max)
      )
        continue;
      const cutoff = Math.min(
        now,
        start,
        Date.parse(profile.allowed_as_of_end),
      );
      if (
        !Number.isFinite(cutoff) ||
        cutoff < Date.parse(profile.allowed_as_of_start)
      )
        continue;
      const seen = assigned[profile.spatial_level];
      const ids = profile.route_ids
        .filter((id) => valid.has(id) && !seen.has(id))
        .sort();
      for (const id of ids) seen.add(id);
      for (let offset = 0; offset < ids.length; offset += limit) {
        plan.push({
          dataset_revision_id: caps.dataset_revision_id,
          profile_id: profile.id,
          route_ids: ids.slice(offset, offset + limit),
          forecast_start: dayStart(day),
          as_of: new Date(cutoff).toISOString(),
        });
      }
    }
  }
  return plan;
}

export function findDemandRun(runs, request) {
  return runs.find(
    (run) =>
      ["succeeded", "queued", "running"].includes(run.status) &&
      run.profile.id === request.profile_id &&
      Date.parse(run.forecast_start) === Date.parse(request.forecast_start) &&
      Date.parse(run.as_of) === Date.parse(request.as_of) &&
      request.route_ids.every((id) => run.route_ids.includes(id)),
  );
}

export function classifyDemand(value, mean) {
  if (!Number.isFinite(value) || !Number.isFinite(mean)) return "unknown";
  if (mean === 0) return "low";
  const ratio = value / mean;
  if (ratio >= 1.5) return "peak";
  if (ratio >= 1.2) return "high";
  return ratio < 0.8 ? "low" : "typical";
}

export const routeDemandKey = (id) => `route:${id}`;
export const stopDemandKey = (route, stop) => `stop:${route}:${stop}`;

export function demandIndex(points) {
  const groups = new Map();
  for (const point of points) {
    const { spatial } = point;
    const hour = Date.parse(point.interval_start);
    const key =
      spatial.level === "route"
        ? routeDemandKey(spatial.route_id)
        : stopDemandKey(spatial.route_id, spatial.stop_id);
    if (!groups.has(key)) groups.set(key, new Map());
    const series = groups.get(key);
    const previous = series.has(hour) ? series.get(hour) : 0;
    series.set(
      hour,
      Number.isFinite(previous) && Number.isFinite(point.value)
        ? previous + point.value
        : null,
    );
  }
  const result = new Map();
  for (const [key, series] of groups) {
    const days = new Map();
    for (const [hour, value] of series) {
      if (!Number.isFinite(value)) continue;
      const day = localDay(hour);
      const summary = days.get(day) || { sum: 0, count: 0 };
      summary.sum += value;
      summary.count += 1;
      days.set(day, summary);
    }
    result.set(key, { series, days });
  }
  return result;
}

export function demandAt(index, key, hour) {
  const group = index.get(key);
  const value = group?.series.get(hour) ?? null;
  const day = group?.days.get(localDay(hour));
  const mean = day?.count === 24 ? day.sum / day.count : null;
  return { value, mean, band: classifyDemand(value, mean) };
}
