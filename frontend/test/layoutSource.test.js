import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";


test("mobile map attribution remains at the bottom edge", () => {
  const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");
  const mobileAttributionPosition = css.match(
    /\.content \.leaflet-bottom\.leaflet-right\s*\{([^}]+)\}/,
  )?.[1];

  assert.match(mobileAttributionPosition, /top:\s*auto/);
  assert.match(mobileAttributionPosition, /bottom:\s*0/);
});

test("transit navigation links back to financial research", () => {
  const navigation = readFileSync(
    new URL("../src/PortfolioNav.jsx", import.meta.url),
    "utf8",
  );

  assert.match(
    navigation,
    /\["Financial Research", "\/research\/financials"\]/,
  );
});
