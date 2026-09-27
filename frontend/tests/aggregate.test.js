import test from "node:test";
import assert from "node:assert/strict";
import {
  endFromInput,
  fromInput,
  groupOptions,
  lastInput,
  levelName,
  spatialLabel,
  toInput,
} from "../src/domain/aggregate.js";

test("period inputs round-trip on each profile grid in Moscow time", () => {
  const start = "2026-09-20T21:00:00+00:00"; // 2026-09-21 00:00 MSK
  assert.equal(toInput(start, "hour"), "2026-09-21T00:00");
  assert.equal(toInput(start, "day"), "2026-09-21");
  assert.equal(
    fromInput("2026-09-21T07:30", "hour"),
    "2026-09-21T07:00:00+03:00",
  );
  assert.equal(fromInput("2026-09-21", "day"), "2026-09-21T00:00:00+03:00");
  assert.equal(fromInput("2026-10", "month"), "2026-10-01T00:00:00+03:00");
});

test("the inclusive last bucket becomes the exclusive API end", () => {
  assert.equal(
    endFromInput("2026-09-21T09:00", "hour"),
    "2026-09-21T10:00:00+03:00",
  );
  assert.equal(endFromInput("2026-09-30", "day"), "2026-10-01T00:00:00+03:00");
  assert.equal(endFromInput("2026-12", "month"), "2027-01-01T00:00:00+03:00");
  assert.equal(
    lastInput("2026-09-21T21:00:00+00:00", "hour"),
    "2026-09-21T23:00",
  );
  assert.equal(lastInput("2026-10-20T21:00:00+00:00", "day"), "2026-10-20");
  assert.equal(lastInput("2027-09-30T21:00:00+00:00", "month"), "2027-09");
  assert.equal(lastInput("2027-01-01T00:00:00+03:00", "month"), "2026-12");
});

test("groupings never go finer than the grid or outside the spatial level", () => {
  const values = (resolution, level) =>
    groupOptions(resolution, level).map((o) => o.value);
  assert.deepEqual(values("hour", "stop"), [
    "none",
    "hour",
    "day",
    "month",
    "direction",
    "stop",
  ]);
  assert.deepEqual(values("day", "route"), ["none", "day", "month"]);
  assert.deepEqual(values("month", "segment"), [
    "none",
    "month",
    "direction",
    "segment",
  ]);
});

test("spatial groups are labelled from the route catalogue", () => {
  const route = {
    route: { id: "r", number: "17" },
    stops: [
      { id: "a", name: "Депо" },
      { id: "b", name: "Парк" },
    ],
    directions: [
      {
        id: "out",
        name: "Прямое",
        segments: [{ id: "g", from_stop_id: "a", to_stop_id: "b" }],
      },
    ],
  };
  assert.equal(spatialLabel({ route_id: "r" }, route), "Маршрут 17");
  assert.equal(spatialLabel({ direction_id: "out" }, route), "Прямое");
  assert.equal(
    spatialLabel({ stop_id: "b", stop_sequence: 2 }, route),
    "2. Парк",
  );
  assert.equal(spatialLabel({ segment_id: "g" }, route), "Депо → Парк");
});

test("profile labels tell stop-level forecasts from route totals", () => {
  assert.equal(levelName("route"), "");
  assert.equal(levelName("stop"), " · по остановкам");
  assert.equal(levelName("segment"), " · по участкам");
});
