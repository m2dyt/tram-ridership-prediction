// Bounding box [[west, south], [east, north]] of GeoJSON features, or null if there are no coordinates.
export function featureBounds(features) {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  const visit = (coordinates) => {
    if (!Array.isArray(coordinates)) return;
    if (typeof coordinates[0] === "number") {
      const [lon, lat] = coordinates;
      if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;
      west = Math.min(west, lon);
      east = Math.max(east, lon);
      south = Math.min(south, lat);
      north = Math.max(north, lat);
      return;
    }
    coordinates.forEach(visit);
  };
  for (const feature of features || []) visit(feature?.geometry?.coordinates);
  return Number.isFinite(west)
    ? [
        [west, south],
        [east, north],
      ]
    : null;
}
