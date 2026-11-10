import test from "node:test";
import assert from "node:assert/strict";
import { fetchModelCatalog } from "../src/api/modelCatalog.js";

test("preserves the server warning even when there are no model artifacts", async () => {
  const catalog = await fetchModelCatalog(
    async () => ({
      items: [],
      active_version_error: "Active version file is invalid",
    }),
    {},
  );
  assert.deepEqual(catalog.items, []);
  assert.equal(catalog.activeVersionError, "Active version file is invalid");
});

test("does not invent a warning when the server returns none", async () => {
  const catalog = await fetchModelCatalog(
    async () => ({
      items: [{ id: "v1", status: "available" }],
    }),
    {},
  );
  assert.equal(catalog.activeVersionError, null);
  assert.equal(catalog.items[0].id, "v1");
});
