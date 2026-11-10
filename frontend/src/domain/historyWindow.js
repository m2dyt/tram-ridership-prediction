const MOSCOW_OFFSET = 3 * 60 * 60 * 1000;
const DAY = 24 * 60 * 60 * 1000;

export function initialHistoryWindow(profile) {
  const end = Date.parse(profile.history_end);
  const availableStart = Date.parse(profile.history_start);
  let limitedStart = end - 366 * DAY;
  if (profile.resolution === "month") {
    const localEnd = new Date(end + MOSCOW_OFFSET);
    limitedStart =
      Date.UTC(localEnd.getUTCFullYear() - 1, localEnd.getUTCMonth(), 1) -
      MOSCOW_OFFSET;
  }
  return {
    from: new Date(Math.max(availableStart, limitedStart)).toISOString(),
    to: new Date(end).toISOString(),
  };
}
