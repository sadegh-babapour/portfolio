"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const cors = require("cors");

const { isAllowedOrigin } = require("../config/transitConfig");

test("the public site and local development are allowed", () => {
  for (const origin of [
    "https://bizqlab.com",
    "https://www.bizqlab.com",
    "http://localhost:5173",
    "http://127.0.0.1:8086",
    "http://[::1]:5173",
  ]) {
    assert.equal(isAllowedOrigin(origin), true, origin);
  }
});

test("other sites and look-alike origins are refused", () => {
  for (const origin of [
    "https://evil.example",
    "http://bizqlab.com",
    "https://bizqlab.com.evil.example",
    "https://evilbizqlab.com",
    "https://www.bizqlab.com:8443",
    "https://localhost:5173",
    "http://localhost.evil.example",
    "http://192.168.1.20:5173",
    "null",
    "",
    undefined,
  ]) {
    assert.equal(isAllowedOrigin(origin), false, String(origin));
  }
});

function corsHeaders(origin) {
  const middleware = cors({ origin: (requestOrigin, callback) => callback(null, isAllowedOrigin(requestOrigin)) });
  const headers = {};
  const request = { method: "GET", headers: origin ? { origin } : {} };
  const response = {
    getHeader: (name) => headers[name.toLowerCase()],
    setHeader: (name, value) => { headers[name.toLowerCase()] = value; },
  };
  return new Promise((resolve) => middleware(request, response, () => resolve(headers)));
}

test("the middleware echoes only allowed origins", async () => {
  assert.equal((await corsHeaders("https://www.bizqlab.com"))["access-control-allow-origin"], "https://www.bizqlab.com");
  assert.equal((await corsHeaders("https://evil.example"))["access-control-allow-origin"], undefined);
  assert.equal((await corsHeaders(undefined))["access-control-allow-origin"], undefined);
});

test("the server uses the allow-list instead of open CORS", () => {
  const server = fs.readFileSync(path.join(__dirname, "..", "server.js"), "utf8");
  assert.doesNotMatch(server, /cors\(\s*\)/);
  assert.match(server, /cors\(\{ origin: \(origin, callback\) => callback\(null, isAllowedOrigin\(origin\)\) \}\)/);
});
