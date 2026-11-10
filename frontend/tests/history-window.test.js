import test from "node:test";
import assert from "node:assert/strict";

import * as history from "../src/domain/historyWindow.js";

const initialWindow = (resolution, history_start, history_end) =>
  history.initialHistoryWindow?.({ resolution, history_start, history_end });

test("limits long hourly history to 366 days before its end", () => {
  assert.deepEqual(
    initialWindow(
      "hour",
      "2020-01-01T00:00:00+03:00",
      "2026-11-01T00:00:00+03:00",
    ),
    {
      from: "2025-10-30T21:00:00.000Z",
      to: "2026-10-31T21:00:00.000Z",
    },
  );
});

test("preserves a short history rather than extending it", () => {
  assert.deepEqual(
    initialWindow(
      "day",
      "2026-10-20T00:00:00+03:00",
      "2026-11-01T00:00:00+03:00",
    ),
    {
      from: "2026-10-19T21:00:00.000Z",
      to: "2026-10-31T21:00:00.000Z",
    },
  );
});

test("daily grid remains aligned across a leap day", () => {
  assert.deepEqual(
    initialWindow(
      "day",
      "2020-01-01T00:00:00+03:00",
      "2025-03-01T00:00:00+03:00",
    ),
    {
      from: "2024-02-28T21:00:00.000Z",
      to: "2025-02-28T21:00:00.000Z",
    },
  );
});

test("monthly grid includes at most 12 calendar months", () => {
  assert.deepEqual(
    initialWindow(
      "month",
      "2020-01-01T00:00:00+03:00",
      "2025-03-01T00:00:00+03:00",
    ),
    {
      from: "2024-02-29T21:00:00.000Z",
      to: "2025-02-28T21:00:00.000Z",
    },
  );
});

test("preserves a short monthly history", () => {
  assert.deepEqual(
    initialWindow(
      "month",
      "2024-11-01T00:00:00+03:00",
      "2025-03-01T00:00:00+03:00",
    ),
    {
      from: "2024-10-31T21:00:00.000Z",
      to: "2025-02-28T21:00:00.000Z",
    },
  );
});
