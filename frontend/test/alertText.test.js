import assert from "node:assert/strict";
import test from "node:test";

import { alertText } from "../src/alertText.js";


test("alert markup becomes readable inert text", () => {
  assert.equal(
    alertText("<p>Route &amp; stop<br>Use platform 2</p>"),
    "Route & stop\nUse platform 2",
  );
});

test("active markup and event attributes cannot reach the rendered value", () => {
  const result = alertText(
    '<script>alert("bad")</script><img src=x onerror=alert(1)><b>Detour</b>',
  );
  assert.equal(result, "Detour");
  assert.doesNotMatch(result, /script|onerror|<|>/i);
});
