import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { createGlideGuard } from "../src/glideGuard.js";


function fakeFrames() {
  let nextId = 1;
  const queue = new Map();
  return {
    requestFrame: (callback) => {
      const id = nextId++;
      queue.set(id, callback);
      return id;
    },
    cancelFrame: (id) => queue.delete(id),
    flush() {
      const callbacks = [...queue.values()];
      queue.clear();
      callbacks.forEach((callback) => callback());
    },
  };
}

function fakeContainer() {
  const classes = new Set();
  return {
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
    },
    has: (name) => classes.has(name),
  };
}


test("glide is off from zoom start until two frames after zoom end", () => {
  const frames = fakeFrames();
  const container = fakeContainer();
  const guard = createGlideGuard(container, frames);

  guard.start();
  assert.equal(container.has("map-zooming"), true);
  guard.end();
  assert.equal(container.has("map-zooming"), true);
  frames.flush();
  assert.equal(container.has("map-zooming"), true, "still off after one frame");
  frames.flush();
  assert.equal(container.has("map-zooming"), false);
});

test("a new zoom before the glide returns keeps it off", () => {
  const frames = fakeFrames();
  const container = fakeContainer();
  const guard = createGlideGuard(container, frames);

  guard.start();
  guard.end();
  frames.flush();
  guard.start();
  frames.flush();
  frames.flush();
  assert.equal(container.has("map-zooming"), true);
  guard.end();
  frames.flush();
  frames.flush();
  assert.equal(container.has("map-zooming"), false);
});

test("dispose removes the class and pending frames", () => {
  const frames = fakeFrames();
  const container = fakeContainer();
  const guard = createGlideGuard(container, frames);

  guard.start();
  guard.end();
  guard.dispose();
  assert.equal(container.has("map-zooming"), false);
  frames.flush();
  assert.equal(container.has("map-zooming"), false);
});

test("bus markers glide only outside zooms and respect reduced motion", () => {
  const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");
  assert.match(
    css,
    /@media \(prefers-reduced-motion: no-preference\)\s*\{\s*\.map:not\(\.map-zooming\) \.leaflet-marker-icon\.bus-marker-glide\s*\{\s*transition:\s*transform 1s linear;/,
  );
  assert.equal(css.match(/bus-marker/g).length, 1, "no other rule overrides the glide");
});
