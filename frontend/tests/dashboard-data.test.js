import test from "node:test";
import assert from "node:assert/strict";

import * as data from "../src/domain/dashboardData.js";

test("selects only an hourly additive route profile for the map", () => {
  const profiles = [
    {
      id: "daily",
      route_ids: ["1"],
      spatial_level: "route",
      resolution: "day",
      metric: "validations",
      aggregation_method: "sum",
    },
    {
      id: "stops",
      route_ids: ["1"],
      spatial_level: "stop",
      resolution: "hour",
      metric: "validations",
      aggregation_method: "sum",
    },
    {
      id: "ratio",
      route_ids: ["1"],
      spatial_level: "route",
      resolution: "hour",
      metric: "occupancy_ratio",
      aggregation_method: "mean",
    },
    {
      id: "hourly",
      route_ids: ["1"],
      spatial_level: "route",
      resolution: "hour",
      metric: "validations",
      aggregation_method: "sum",
    },
  ];
  assert.equal(data.mapObservationProfile?.(profiles, "1")?.id, "hourly");
  assert.equal(data.mapObservationProfile?.(profiles, "2"), null);
});

test("dashboard uses a route-level profile for the selected route only", () => {
  const profiles = [
    {
      id: "other",
      route_ids: ["2"],
      spatial_level: "route",
      resolution: "hour",
    },
    { id: "stop", route_ids: ["1"], spatial_level: "stop", resolution: "hour" },
    { id: "day", route_ids: ["1"], spatial_level: "route", resolution: "day" },
    {
      id: "hour",
      route_ids: ["1"],
      spatial_level: "route",
      resolution: "hour",
    },
  ];
  assert.equal(data.dashboardObservationProfile?.(profiles, "1")?.id, "hour");
  assert.equal(data.dashboardObservationProfile?.(profiles, "3"), null);
});

test("counts each route with an available forecast only once", () => {
  const profiles = [
    { availability: "available", route_ids: ["1", "2"] },
    { availability: "available", route_ids: ["1", "3"] },
    { availability: "unavailable", route_ids: ["4"] },
  ];
  assert.equal(data.forecastRouteCount?.(profiles), 3);
});

test("observation period stays within actual published history", () => {
  const profile = {
    history_start: "2026-11-01T00:00:00+03:00",
    history_end: "2026-11-10T00:00:00+03:00",
  };
  assert.deepEqual(data.observationWindow?.(profile, 30), {
    from: "2026-10-31T21:00:00.000Z",
    to: "2026-11-09T21:00:00.000Z",
  });
  assert.equal(data.observationWindow?.({}, 30), null);
});

test("monthly observation period stays aligned to Moscow month boundaries", () => {
  const profile = {
    resolution: "month",
    history_start: "2020-01-01T00:00:00+03:00",
    history_end: "2026-11-01T00:00:00+03:00",
  };
  assert.deepEqual(data.observationWindow(profile, 30), {
    from: "2026-09-30T21:00:00.000Z",
    to: "2026-10-31T21:00:00.000Z",
  });
});
