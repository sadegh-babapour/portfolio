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

test("the retired financial research page is not in the navigation", () => {
  const navigation = JSON.parse(readFileSync(
    new URL("../../content/navigation.json", import.meta.url),
    "utf8",
  ));

  assert.equal(navigation.links.some(([, href]) => href.startsWith("/research")), false);
});

test("the transit header takes its links from the shared navigation file", () => {
  const source = readFileSync(new URL("../src/PortfolioNav.jsx", import.meta.url), "utf8");
  const navigation = JSON.parse(readFileSync(
    new URL("../../content/navigation.json", import.meta.url),
    "utf8",
  ));

  assert.match(source, /import navigation from "\.\.\/\.\.\/content\/navigation\.json"/);
  assert.doesNotMatch(source, /\["Home", "\/"\]/, "no second copy of the links");
  assert.ok(navigation.links.some(([, href]) => href === "/calgary-transit-live/"));
});

test("the transit header uses the shared header stylesheet", () => {
  const source = readFileSync(new URL("../src/PortfolioNav.jsx", import.meta.url), "utf8");
  const appCss = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");
  const shared = readFileSync(new URL("../../static/portfolio-nav.css", import.meta.url), "utf8");

  assert.match(source, /import "\.\.\/\.\.\/static\/portfolio-nav\.css";/);
  assert.doesNotMatch(appCss, /\.portfolio-/, "no second copy of the header styles");
  for (const className of source.matchAll(/className="(portfolio-[a-z-]+)"/g)) {
    assert.match(shared, new RegExp(`\\.${className[1]}\\b`), className[1]);
  }
});

test("map tiles overlap so no seams show between them", () => {
  const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");
  const rule = css.match(/\.leaflet-container img\.leaflet-tile \{([^}]*)\}/);

  assert.ok(rule, "tile overlap rule");
  assert.match(rule[1], /mix-blend-mode: normal;/);
  assert.match(rule[1], /width: 257px !important;/);
  assert.match(rule[1], /height: 257px !important;/);
});
