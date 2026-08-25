import assert from "node:assert/strict";
import test from "node:test";

import { isShortBlankMapTap, SHORT_MAP_TAP_MS } from "../src/mapInteraction.js";

test("only a short unmoved blank-map gesture clears a preview", () => {
  assert.equal(isShortBlankMapTap({ durationMs: 120, moved: false, interactiveTarget: false }), true);
  assert.equal(isShortBlankMapTap({ durationMs: SHORT_MAP_TAP_MS + 1, moved: false, interactiveTarget: false }), false);
  assert.equal(isShortBlankMapTap({ durationMs: 120, moved: true, interactiveTarget: false }), false);
  assert.equal(isShortBlankMapTap({ durationMs: 120, moved: false, interactiveTarget: true }), false);
});
