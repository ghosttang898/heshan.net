import test from "node:test";
import assert from "node:assert/strict";
import { createAnalyticsRouterWindow, isAnalyticsEnvironment, isPublicAnalyticsPath, loadCloudflareAnalytics } from "./analytics.js";

function fixture(pathname = "/", hostname = "heshan.net") {
  const calls = [];
  const scripts = [];
  const url = new URL(`https://${hostname}${pathname}`);
  const browser = {
    location: { href: url.href, origin: url.origin, pathname: url.pathname, hostname, protocol: url.protocol,
      assign: (url) => calls.push(["assign", url]), replace: (url) => calls.push(["replace", url]) },
    history: { state: { idx: 0 }, pushState: (...args) => calls.push(["pushState", ...args]),
      replaceState: (...args) => calls.push(["replaceState", ...args]), go: (delta) => calls.push(["go", delta]) },
    document: { getElementById: (id) => scripts.find((script) => script.id === id),
      querySelector: () => scripts[0], createElement: () => ({ setAttribute(key, value) { this[key] = value; } }),
      head: { appendChild: (script) => scripts.push(script) } },
  };
  return { browser, scripts, calls };
}

test("production HTTPS domain allowlist excludes all local/development/staging origins", () => {
  for (const hostname of ["localhost", "127.0.0.1", "::1", "staging.heshan.net", "other.example"]) {
    const { browser } = fixture("/", hostname === "::1" ? "[::1]" : hostname);
    assert.equal(isAnalyticsEnvironment(true, browser.location), false);
  }
  assert.equal(isAnalyticsEnvironment(false, fixture().browser.location), false);
  assert.equal(isAnalyticsEnvironment(true, { ...fixture().browser.location, protocol: "http:" }), false);
  assert.equal(isAnalyticsEnvironment(true, fixture("/", "www.heshan.net").browser.location), true);
});

test("public paths are explicitly allowed, auth/admin/unknown paths fail closed", () => {
  for (const path of ["/", "/chat", "/find/", "/posts/12", "/privacy"]) assert.equal(isPublicAnalyticsPath(path), true);
  for (const path of ["/admin", "/admin/posts", "/admin/users/1", "/login", "/login/", "/register", "/ADMIN", "/posts/sensitive-name", "/unknown"]) assert.equal(isPublicAnalyticsPath(path), false);
});

test("official script loads once and is never loaded in dev or excluded documents", () => {
  const { browser, scripts } = fixture();
  loadCloudflareAnalytics(browser, true); loadCloudflareAnalytics(browser, true);
  assert.equal(scripts.length, 1);
  assert.equal(scripts[0].type, "module");
  assert.deepEqual(JSON.parse(scripts[0]["data-cf-beacon"]), { token: "51e38dcc9b204689b9caa1fdea20a4ba" });
  for (const path of ["/login", "/register", "/admin", "/admin/comments"]) {
    const instance = fixture(path); loadCloudflareAnalytics(instance.browser, true); assert.equal(instance.scripts.length, 0);
  }
  const dev = fixture(); loadCloudflareAnalytics(dev.browser, false); assert.equal(dev.scripts.length, 0);
});

test("router crosses measurement boundaries before calling beacon-instrumented history", () => {
  const { browser, calls } = fixture("/chat");
  const proxy = createAnalyticsRouterWindow(browser, true);
  proxy.history.pushState({ usr: null }, "", "/find");
  proxy.history.pushState({}, "", "/admin/users?search=secret");
  proxy.history.replaceState({}, "", "/login");
  proxy.history.go(-1);
  assert.deepEqual(calls.map((call) => call[0]), ["pushState", "assign", "replace", "go"]);
  assert.equal(calls[1][1], "https://heshan.net/admin/users?search=secret");
  assert.deepEqual(proxy.history.state, { idx: 0 });
  const auth = fixture("/login");
  const authWindow = createAnalyticsRouterWindow(auth.browser, true);
  authWindow.history.replaceState({}, "", "/chat");
  authWindow.history.pushState({}, "", "/admin");
  assert.deepEqual(auth.calls.map((call) => call[0]), ["replace", "pushState"]);
  assert.equal(createAnalyticsRouterWindow(browser, false), browser);
});
