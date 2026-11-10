import test from "node:test";
import assert from "node:assert/strict";
import {
  evaluationScoreRows,
  peakRuleLabel,
} from "../src/domain/evaluationScores.js";

test("retains every method and route slice reported by the API", () => {
  const scores = [
    { method: "model", route_id: null, demand_slice: "all" },
    { method: "seasonal_naive", route_id: "route-1", demand_slice: "peak" },
    { method: "regression", route_id: "route-2", demand_slice: "all" },
  ];
  const rows = evaluationScoreRows(scores, {
    route: { id: "route-1", number: "7" },
  });
  assert.equal(rows.length, 3);
  assert.deepEqual(
    rows.map((row) => row.methodLabel),
    ["Проверяемая модель", "Сезонная база", "Регрессия"],
  );
  assert.deepEqual(
    rows.map((row) => row.routeLabel),
    ["Все маршруты", "Маршрут 7", "route-2"],
  );
  assert.deepEqual(
    rows.map((row) => row.sliceLabel),
    ["Все интервалы", "Часы пик", "Все интервалы"],
  );
});

test("reports a new peak rule supplied by the server without substitution", () => {
  assert.equal(
    peakRuleLabel("custom rule from the report"),
    "custom rule from the report",
  );
});
