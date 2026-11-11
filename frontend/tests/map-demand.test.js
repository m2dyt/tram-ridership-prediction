import test from "node:test";
import assert from "node:assert/strict";
import {
  demandPlan,
  demandIndex,
  demandAt,
  classifyDemand,
  demandRequestKey,
} from "../src/domain/mapDemand.js";

const base = {
  availability: "available",
  horizon: "day",
  resolution: "hour",
  metric: "validations",
  aggregation_method: "sum",
  forecast_start_min: "2026-11-11T00:00:00+03:00",
  forecast_start_max: "2026-11-12T00:00:00+03:00",
  allowed_as_of_start: "2026-11-10T00:00:00+03:00",
  allowed_as_of_end: "2026-11-10T00:00:00+03:00",
};
const routes = ["a", "b"].map((id) => ({
  route: { id, valid_from: "2026-01-01", valid_to: null },
}));

test("plans supported days, batches routes and avoids overlapping profiles", () => {
  const caps = {
    dataset_revision_id: "rev",
    max_routes_per_run: 1,
    forecast_profiles: [
      { ...base, id: "route", spatial_level: "route", route_ids: ["a", "b"] },
      { ...base, id: "duplicate", spatial_level: "route", route_ids: ["a"] },
      { ...base, id: "stops", spatial_level: "stop", route_ids: ["b"] },
    ],
  };
  const plan = demandPlan(
    caps,
    routes,
    "2026-11-11",
    "2026-11-13",
    Date.parse("2026-11-10T09:00:00Z"),
  );
  assert.equal(plan.length, 6);
  assert.deepEqual(
    plan.map(({ profile_id }) => profile_id),
    ["route", "route", "stops", "route", "route", "stops"],
  );
  assert.equal(plan[0].forecast_start, "2026-11-11T00:00:00+03:00");
  assert.equal(plan[0].as_of, "2026-11-09T21:00:00.000Z");
});

test("load is relative to its own day and missing or partial points stay unclassified", () => {
  const points = Array.from({ length: 24 }, (_, hour) => ({
    interval_start: new Date(
      Date.parse("2026-11-11T00:00:00+03:00") + hour * 3600000,
    ).toISOString(),
    spatial: { level: "stop", route_id: "a", stop_id: "1" },
    value: hour === 0 ? 50 : 10,
  }));
  const key = "stop:a:1";
  const index = demandIndex(points);
  assert.equal(
    demandAt(index, key, Date.parse(points[0].interval_start)).band,
    "peak",
  );
  assert.equal(
    demandAt(index, key, Date.parse(points[1].interval_start)).band,
    "typical",
  );
  assert.equal(
    demandAt(
      demandIndex(points.slice(0, 23)),
      key,
      Date.parse(points[0].interval_start),
    ).band,
    "unknown",
  );
  assert.equal(classifyDemand(0, 0), "low");
  assert.equal(classifyDemand(null, 10), "unknown");
});

test("accepts boarding profiles of the published competition data", () => {
  const caps = {
    dataset_revision_id: "rev",
    max_routes_per_run: 100,
    forecast_profiles: [
      {
        ...base,
        id: "route",
        metric: "boardings",
        spatial_level: "route",
        route_ids: ["a"],
      },
      {
        ...base,
        id: "occupancy",
        metric: "occupancy",
        spatial_level: "route",
        route_ids: ["b"],
      },
    ],
  };
  const plan = demandPlan(
    caps,
    routes,
    "2026-11-11",
    "2026-11-11",
    Date.parse("2026-11-10T09:00:00Z"),
  );
  assert.deepEqual(
    plan.map((request) => [request.profile_id, request.route_ids]),
    [["route", ["a"]]],
  );
});

test("the same demand request always gets the same retry key", async () => {
  const request = {
    dataset_revision_id: "rev",
    profile_id: "route",
    route_ids: ["b", "a"],
    forecast_start: "2026-11-11T00:00:00+03:00",
    as_of: "2026-11-09T21:00:00.000Z",
  };
  const key = await demandRequestKey(request);
  assert.equal(
    key,
    await demandRequestKey({ ...request, route_ids: ["a", "b"] }),
  );
  assert.notEqual(
    key,
    await demandRequestKey({
      ...request,
      forecast_start: "2026-11-12T00:00:00+03:00",
    }),
  );
  assert.ok(key.length >= 8 && key.length <= 128);
});
