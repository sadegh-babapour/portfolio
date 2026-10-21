import assert from "node:assert/strict";
import test from "node:test";

import { createRoutePathsCache } from "../src/routePathsCache.js";


test("returns the same array until it is too old", () => {
  const cache = createRoutePathsCache({ maxAgeMs: 1000 });
  const paths = [{ route_short_name: "1" }];
  cache.set("all", paths, 0);

  assert.equal(cache.get("all", 500), paths);
  assert.equal(cache.get("all", 1000), paths);
  assert.equal(cache.get("all", 1001), null);
  assert.equal(cache.get("featured", 0), null);
});

test("keeps the most recently used filters", () => {
  const cache = createRoutePathsCache({ maxAgeMs: 1000, maxEntries: 2 });
  cache.set("all", ["all"], 0);
  cache.set("route 1", ["1"], 0);
  cache.get("all", 0);
  cache.set("route 2", ["2"], 0);

  assert.deepEqual(cache.get("all", 0), ["all"], "selecting a bus and back keeps the full set");
  assert.equal(cache.get("route 1", 0), null);
  assert.deepEqual(cache.get("route 2", 0), ["2"]);
});
