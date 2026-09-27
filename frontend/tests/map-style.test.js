import test from "node:test";
import assert from "node:assert/strict";
import {
  FALLBACK_MAP_STYLE,
  shouldFallbackToLocalMapStyle,
} from "../src/domain/mapStyle.js";

test("switches to an offline map style when the initial style fails", () => {
  const event = {
    error: new Error("Failed to fetch map style"),
    target: { isStyleLoaded: () => false },
  };

  assert.equal(shouldFallbackToLocalMapStyle(event), true);
  assert.deepEqual(FALLBACK_MAP_STYLE.sources, {});
  assert.equal(FALLBACK_MAP_STYLE.layers[0].type, "background");
});

test("does not replace a loaded style for later tile errors", () => {
  const event = {
    error: new Error("Failed to fetch a tile"),
    target: { isStyleLoaded: () => true },
  };

  assert.equal(shouldFallbackToLocalMapStyle(event), false);
  assert.equal(shouldFallbackToLocalMapStyle({}), false);
});

test("does not replace the style for a tile source error during loading", () => {
  const event = {
    error: new Error("Failed to fetch a basemap tile"),
    sourceId: "carto",
    target: { isStyleLoaded: () => false },
  };

  assert.equal(shouldFallbackToLocalMapStyle(event), false);
});
