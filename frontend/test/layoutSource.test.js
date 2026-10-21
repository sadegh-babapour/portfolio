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
  const navigation = JSON.parse(readFileSync(
    new URL("../../content/navigation.json", import.meta.url),
    "utf8",
  ));

  assert.deepEqual(
    navigation.links.find(([label]) => label === "Financial Research"),
    ["Financial Research", "/research/financials"],
  );
});

test("the transit header takes its links from the shared navigation file", () => {
  const source = readFileSync(new URL("../src/PortfolioNav.jsx", import.meta.url), "utf8");
  const navigation = JSON.parse(readFileSync(
    new URL("../../content/navigation.json", import.meta.url),
    "utf8",
  ));

  assert.match(source, /import navigation from "\.\.\/\.\.\/content\/navigation\.json"/);
  assert.doesNotMatch(source, /\["Home", "\/"\]/, "no second copy of the links");
  assert.deepEqual(navigation.links.at(-1), ["Calgary Transit Live", "/calgary-transit-live/"]);
});
