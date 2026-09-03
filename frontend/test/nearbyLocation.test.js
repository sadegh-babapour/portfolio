import assert from "node:assert/strict";
import test from "node:test";

import { usableCachedLocation } from "../src/nearbyLocation.js";

test("an in-memory map location can satisfy later Near Me requests", () => {
  const location = [51.0447, -114.0719];
  assert.equal(usableCachedLocation(location), location);
  assert.equal(usableCachedLocation([51.0447, null]), null);
  assert.equal(usableCachedLocation(null), null);
});
