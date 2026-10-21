import assert from "node:assert/strict";
import test from "node:test";

import { startVisibleInterval } from "../src/visibleInterval.js";


function fakeDocument(visibilityState = "visible") {
  const doc = new EventTarget();
  doc.visibilityState = visibilityState;
  doc.show = () => {
    doc.visibilityState = "visible";
    doc.dispatchEvent(new Event("visibilitychange"));
  };
  doc.hide = () => {
    doc.visibilityState = "hidden";
    doc.dispatchEvent(new Event("visibilitychange"));
  };
  return doc;
}


test("runs at once and then on every interval while visible", (t) => {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const doc = fakeDocument();
  let runs = 0;
  const stop = startVisibleInterval(() => { runs += 1; }, 1000, { doc });

  assert.equal(runs, 1);
  t.mock.timers.tick(3000);
  assert.equal(runs, 4);
  stop();
});

test("pauses while hidden and resumes immediately when shown", (t) => {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const doc = fakeDocument();
  let runs = 0;
  let resumes = 0;
  const stop = startVisibleInterval(() => { runs += 1; }, 1000, {
    doc,
    onResume: () => { resumes += 1; },
  });

  doc.hide();
  t.mock.timers.tick(60_000);
  assert.equal(runs, 1, "no work while the tab is hidden");

  doc.show();
  assert.equal(resumes, 1);
  assert.equal(runs, 2, "catches up as soon as the tab is shown");
  t.mock.timers.tick(1000);
  assert.equal(runs, 3);
  stop();
});

test("a tab opened in the background waits until it is shown", (t) => {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const doc = fakeDocument("hidden");
  let runs = 0;
  const stop = startVisibleInterval(() => { runs += 1; }, 1000, { doc });

  t.mock.timers.tick(5000);
  assert.equal(runs, 0);
  doc.show();
  assert.equal(runs, 1);
  stop();
});

test("cleanup stops the interval and the visibility listener", (t) => {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const doc = fakeDocument();
  let runs = 0;
  const stop = startVisibleInterval(() => { runs += 1; }, 1000, { doc });

  stop();
  t.mock.timers.tick(5000);
  doc.hide();
  doc.show();
  assert.equal(runs, 1);
});

test("a repeated visible event does not start a second interval", (t) => {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const doc = fakeDocument();
  let runs = 0;
  const stop = startVisibleInterval(() => { runs += 1; }, 1000, { doc });

  doc.show();
  t.mock.timers.tick(1000);
  assert.equal(runs, 2);
  stop();
});
