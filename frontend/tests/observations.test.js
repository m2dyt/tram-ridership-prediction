import test from "node:test";
import assert from "node:assert/strict";
import {
  fetchObservationPages,
  fetchPages,
} from "../src/api/observationPages.js";

test("loads every observation page while preserving the selected filters", async () => {
  const calls = [];
  const rows = await fetchObservationPages(
    async (path, params) => {
      calls.push({ path, params });
      return calls.length === 1
        ? {
            items: [{ value: 1 }],
            page: { has_more: true, next_cursor: "next" },
          }
        : {
            items: [{ value: 2 }],
            page: { has_more: false, next_cursor: null },
          };
    },
    { route_id: "r1", from: "2026-01-01" },
  );
  assert.deepEqual(rows, [{ value: 1 }, { value: 2 }]);
  assert.equal(calls[1].params.cursor, "next");
  assert.equal(calls[1].params.route_id, "r1");
});

test("loads evaluation points across pages at the requested endpoint", async () => {
  const paths = [];
  const rows = await fetchPages(
    async (path, params) => {
      paths.push(path);
      return params.cursor
        ? { items: [{ value: 2 }], page: { has_more: false } }
        : {
            items: [{ value: 1 }],
            page: { has_more: true, next_cursor: "next" },
          };
    },
    "/evaluations/eval-1/points",
    { fold_id: "fold-1" },
  );
  assert.deepEqual(rows, [{ value: 1 }, { value: 2 }]);
  assert.deepEqual(paths, [
    "/evaluations/eval-1/points",
    "/evaluations/eval-1/points",
  ]);
});

test("rejects a repeated cursor instead of requesting indefinitely", async () => {
  await assert.rejects(
    fetchObservationPages(
      async () => ({
        items: [],
        page: { has_more: true, next_cursor: "same" },
      }),
      {},
    ),
    /страниц/,
  );
});

test("saved runs, evaluation reports and context snapshots retain filters across pages", async () => {
  for (const endpoint of [
    "/forecast-runs",
    "/evaluations",
    "/context/snapshots",
  ]) {
    const requests = [];
    const rows = await fetchPages(
      async (path, params) => {
        requests.push({ path, params });
        return params.cursor
          ? { items: [2], page: { has_more: false } }
          : { items: [1], page: { has_more: true, next_cursor: "next" } };
      },
      endpoint,
      { dataset_revision_id: "v1" },
    );
    assert.deepEqual(rows, [1, 2]);
    assert.equal(requests[1].path, endpoint);
    assert.equal(requests[1].params.dataset_revision_id, "v1");
  }
});
