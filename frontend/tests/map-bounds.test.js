import test from "node:test";
import assert from "node:assert/strict";
import { featureBounds } from "../src/domain/mapBounds.js";

test("bounds cover lines and points of every feature", () => {
  const bounds = featureBounds([
    {
      geometry: {
        type: "MultiLineString",
        coordinates: [
          [
            [37.61, 55.82],
            [37.64, 55.87],
          ],
        ],
      },
    },
    { geometry: { type: "Point", coordinates: [37.6, 55.83] } },
  ]);
  assert.deepEqual(bounds, [
    [37.6, 55.82],
    [37.64, 55.87],
  ]);
});

test("no coordinates give no bounds", () => {
  assert.equal(featureBounds([]), null);
  assert.equal(featureBounds([{ geometry: null }]), null);
});
