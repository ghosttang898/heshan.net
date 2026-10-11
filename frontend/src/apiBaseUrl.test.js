import test from "node:test";
import assert from "node:assert/strict";
import { resolveApiBaseUrl } from "./apiBaseUrl.js";

test("development proxy and HTTPS production API configuration", () => {
  assert.equal(resolveApiBaseUrl(undefined, false), "/api");
  assert.equal(resolveApiBaseUrl("https://api.heshan.net/api/", true), "https://api.heshan.net/api");
  assert.equal(resolveApiBaseUrl("http://localhost:8080/api", false), "http://localhost:8080/api");
});
test("production rejects credentials, sensitive query values, and insecure origins", () => {
  for (const url of ["http://api.heshan.net/api", "https://user:password@api.heshan.net/api",
    "https://api.heshan.net/api?token=fixture", "https://api.heshan.net/api#secret", "https://api.heshan.net/other"]) {
    assert.throws(() => resolveApiBaseUrl(url, true));
  }
});
