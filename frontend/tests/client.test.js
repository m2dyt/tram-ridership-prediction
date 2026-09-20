import test from "node:test";
import assert from "node:assert/strict";
import { createClient, ApiError } from "../src/api/client.js";
import { chartSegments, csvCell, localInput } from "../src/domain/format.js";

test("pagination retains filters and token, fetches all pages", async () => {
  const calls = [];
  const api = createClient("private-token", async (url, options) => {
    calls.push([url, options]);
    return new Response(
      JSON.stringify({
        items: [calls.length],
        page: { has_more: calls.length === 1, next_cursor: "cursor-2" },
      }),
      { status: 200 },
    );
  });
  assert.deepEqual(
    await api.all("/observations", { route_id: "route 1" }),
    [1, 2],
  );
  assert.match(calls[1][0], /route_id=route\+1/);
  assert.match(calls[1][0], /cursor=cursor-2/);
  assert.equal(calls[1][1].headers.Authorization, "Bearer private-token");
});
test("errors retain correlation and never contain the token", async () => {
  const api = createClient(
    "secret",
    async () =>
      new Response(
        JSON.stringify({
          message: "Forbidden",
          code: "FORBIDDEN",
          request_id: "request-1",
        }),
        { status: 403 },
      ),
  );
  await assert.rejects(
    api.request("/context/refresh", { body: {} }),
    (e) =>
      e instanceof ApiError &&
      e.status === 403 &&
      e.requestId === "request-1" &&
      !e.message.includes("secret"),
  );
});
test("gaps break chart lines and CSV formulas are escaped", () => {
  assert.deepEqual(
    chartSegments([{ value: 1 }, { value: null }, { value: 3 }]),
    [[[0, 1]], [[2, 3]]],
  );
  assert.equal(csvCell("=1+1"), '"\'=1+1"');
  assert.equal(csvCell('a"b'), '"a""b"');
  assert.equal(localInput("2026-09-20T21:00:00Z"), "2026-09-21T00:00");
});
