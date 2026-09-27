export const CARTO_MAP_STYLE =
  "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

export const FALLBACK_MAP_STYLE = {
  version: 8,
  sources: {},
  layers: [
    {
      id: "map-background",
      type: "background",
      paint: { "background-color": "#edf2f6" },
    },
  ],
};

export function shouldFallbackToLocalMapStyle(event) {
  const map = event?.target;
  if (
    !event?.error ||
    event.sourceId != null ||
    typeof map?.isStyleLoaded !== "function"
  ) {
    return false;
  }

  try {
    return !map.isStyleLoaded();
  } catch {
    return false;
  }
}
