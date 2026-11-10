const routeProfiles = (profiles, routeId) =>
  (profiles || []).filter(
    (profile) =>
      routeId &&
      profile.spatial_level === "route" &&
      profile.route_ids?.includes(routeId),
  );

export function mapObservationProfile(profiles, routeId) {
  return (
    routeProfiles(profiles, routeId).find(
      (profile) =>
        profile.resolution === "hour" &&
        ["validations", "boardings"].includes(profile.metric) &&
        profile.aggregation_method === "sum",
    ) || null
  );
}

export function dashboardObservationProfile(profiles, routeId) {
  const matching = routeProfiles(profiles, routeId);
  for (const resolution of ["hour", "day", "month"]) {
    const profile = matching.find((item) => item.resolution === resolution);
    if (profile) return profile;
  }
  return null;
}

export function forecastRouteCount(profiles) {
  return new Set(
    (profiles || [])
      .filter((profile) => profile.availability === "available")
      .flatMap((profile) => profile.route_ids || []),
  ).size;
}

export function observationWindow(profile, days) {
  const end = Date.parse(profile?.history_end);
  if (!Number.isFinite(end)) return null;
  const historyStart = Date.parse(profile?.history_start);
  let desiredStart = end - days * 86400000;
  if (profile?.resolution === "month") {
    const moscow = new Date(end + 3 * 3600000);
    desiredStart =
      Date.UTC(
        moscow.getUTCFullYear(),
        moscow.getUTCMonth() - Math.max(1, Math.ceil(days / 30)),
        1,
      ) -
      3 * 3600000;
  }
  const from = Math.max(
    desiredStart,
    Number.isFinite(historyStart) ? historyStart : -Infinity,
  );
  if (from >= end) return null;
  return {
    from: new Date(from).toISOString(),
    to: new Date(end).toISOString(),
  };
}
