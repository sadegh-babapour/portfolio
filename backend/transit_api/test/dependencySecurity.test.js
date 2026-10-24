"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { Readable } = require("node:stream");
const express = require("express");
const proxyaddr = require("proxy-addr");
const qs = require("qs");

// Exercise HTTP middleware in memory: no listening socket or database is needed.
function request(app, { body = "", url = "/", headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const req = Readable.from([Buffer.from(body)]);
    Object.assign(req, {
      method: "POST",
      url,
      headers: {
        "content-type": "application/json",
        "content-length": String(Buffer.byteLength(body)),
        ...headers,
      },
      socket: { remoteAddress: "203.0.113.10" },
    });
    const res = new http.ServerResponse(req);
    res.end = (data) => resolve({ status: res.statusCode, body: JSON.parse(String(data)) });
    app.handle(req, res, reject);
  });
}

function jsonApp() {
  const app = express();
  app.use(express.json()); // Same default parser and limit as server.js.
  app.post("/", (req, res) => res.json({ body: req.body, ip: req.ip }));
  app.use((error, req, res, next) => res.status(error.status || 500).json({ type: error.type }));
  return app;
}

test("IPv4-mapped trust subnets do not trust unrelated IPv4 clients (GHSA-jqcg)", () => {
  const trust = proxyaddr.compile("::ffff:10.0.0.0/8");
  assert.equal(trust("203.0.113.10"), false);
  const correctlyMapped = proxyaddr.compile("::ffff:10.0.0.0/104");
  assert.equal(correctlyMapped("10.0.0.1"), true);
  assert.equal(correctlyMapped("203.0.113.10"), false);
});

test("the default Express trust setting ignores spoofed forwarded IPs", async () => {
  const app = jsonApp();
  assert.equal(app.get("trust proxy"), false);
  const result = await request(app, { body: "{}", headers: { "x-forwarded-for": "192.0.2.1" } });
  assert.equal(result.status, 200);
  assert.equal(result.body.ip, "203.0.113.10");
});

test("qs enforces comma array limits for bracket keys (GHSA-x5fp)", () => {
  assert.throws(() => qs.parse("a[]=1,2,3,4", {
    comma: true, arrayLimit: 3, throwOnLimitExceeded: true,
  }), RangeError);
});

test("qs safely reserializes a parsed constructor.isBuffer value (GHSA-4mjr)", () => {
  const parsed = qs.parse("x[constructor][isBuffer]=y", { plainObjects: true });
  assert.equal(qs.stringify(parsed), "x%5Bconstructor%5D%5BisBuffer%5D=y");
});

test("qs comma serialization accepts null entries (GHSA-q8mj)", () => {
  assert.equal(qs.stringify({ a: [null, "b"] }, {
    arrayFormat: "comma", encodeValuesOnly: true,
  }), "a=,b");
});

test("JSON parser rejects invalid size limits at construction (GHSA-v422)", () => {
  assert.throws(() => express.json({ limit: "not-a-size" }), TypeError);
});

test("JSON parser preserves valid bodies and rejects malformed or oversized ones", async () => {
  const app = jsonApp();
  const valid = await request(app, { body: '{"lat":51.05,"lon":-114.07}' });
  assert.equal(valid.status, 200);
  assert.deepEqual(valid.body.body, { lat: 51.05, lon: -114.07 });
  const malformed = await request(app, { body: '{"lat":' });
  assert.equal(malformed.status, 400);
  assert.equal(malformed.body.type, "entity.parse.failed");
  const oversized = await request(app, { body: JSON.stringify({ data: "x".repeat(101 * 1024) }) });
  assert.equal(oversized.status, 413);
  assert.equal(oversized.body.type, "entity.too.large");
  assert.equal((await request(app, { body: "{}" })).status, 200);
});
