// MapLibre 6 loads its worker from a file next to its own module, which Vite
// merges into one chunk: in a production build that worker URL answers with
// index.html and the map never renders. Bundle the worker (with the shared
// chunk it imports) as a separate file and point MapLibre at it before any map
// is created; both map components pass this promise as `mapLib`.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

export const mapLib = import("maplibre-gl").then((maplibre) => {
  maplibre.setWorkerUrl(workerUrl);
  return maplibre;
});
