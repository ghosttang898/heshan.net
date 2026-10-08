const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const { chromium } = require("playwright");

const preview = process.env.TEST_PREVIEW_URL || "http://127.0.0.1:5174";
const dev = process.env.TEST_DEV_URL || "http://127.0.0.1:5173";
const origin = "https://heshan.net";
const scriptUrl = "https://static.cloudflareinsights.com/beacon.min.js";
const secret = "sensitive-query-marker";
const user = { id: 1, username: "private-user-marker", displayName: "private-name-marker", role: "ADMIN", token: "private-jwt-marker", email: "private-email-marker@example.test" };
const dashboard = { totalUsers: 1, totalPosts: 1, totalComments: 1, todayNewUsers: 0, todayNewPosts: 0, todayNewComments: 0, recentPosts: [], recentUsers: [] };

async function setup(browser, beacon, fallback = false) {
  const context = await browser.newContext();
  const scripts = [];
  const payloads = [];
  const errors = [];
  const documents = [];
  await context.addInitScript(({ user, fallback }) => {
    localStorage.setItem("tonghehui_auth", JSON.stringify(user));
    if (fallback) Object.defineProperty(window, "navigation", { value: undefined, configurable: true });
  }, { user, fallback });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.href === scriptUrl) {
      scripts.push(url.href);
      return route.fulfill({ contentType: "text/javascript", body: beacon, headers: { "access-control-allow-origin": "*" } });
    }
    if (url.hostname === "cloudflareinsights.com" || url.pathname.startsWith("/cdn-cgi/rum")) {
      if (request.method() === "POST") {
        payloads.push(JSON.parse(request.postData()));
        assert.equal(request.headers().authorization, undefined);
      }
      return route.fulfill({ status: 204, headers: { "access-control-allow-origin": origin,
        "access-control-allow-credentials": "true", "access-control-allow-methods": "POST, OPTIONS", "access-control-allow-headers": "content-type" } });
    }
    if ([origin, new URL(preview).origin, new URL(dev).origin].includes(url.origin)) {
      if (url.pathname.startsWith("/api/")) {
        let data;
        if (url.pathname === "/api/health") data = { status: "ok" };
        else if (url.pathname.startsWith("/api/auth/")) data = user;
        else if (url.pathname === "/api/admin/dashboard") data = dashboard;
        else if (/^\/api\/posts\/\d+$/.test(url.pathname)) data = { id: 1, title: "测试帖子", content: "公开内容", type: "CHAT", createdAt: "2026-10-01T12:00:00" };
        else data = [];
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(data) });
      }
      if (request.isNavigationRequest()) documents.push(url.pathname);
      const localUrl = url.origin === origin ? preview + url.pathname + url.search : url.href;
      return route.fulfill({ response: await context.request.get(localUrl) });
    }
    // Never send fixtures or page measurements to an external service.
    return route.abort();
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  const settle = () => page.waitForLoadState("networkidle");
  const views = () => payloads.filter((payload) => payload.eventType === 1);
  return { context, page, scripts, payloads, errors, documents, settle, views };
}

async function scenario(browser, beacon, fallback) {
  const s = await setup(browser, beacon, fallback);
  const { page } = s;
  await page.goto(origin + "/?jwt=" + secret + "#email=" + secret); await s.settle();
  await page.getByRole("link", { name: "聊天广场", exact: true }).click(); await s.settle();
  await page.getByRole("link", { name: "寻人信息", exact: true }).click(); await s.settle();
  await page.goBack(); await s.settle();
  await page.goForward(); await s.settle();
  assert.equal(s.scripts.length, 1);
  assert.equal(s.documents.length, 1, "public links/back/forward remain SPA navigations");
  await page.getByRole("link", { name: "管理后台", exact: true }).click(); await s.settle();
  await page.getByRole("heading", { name: "社区总览" }).waitFor();
  assert.equal(s.scripts.length, 1);
  assert.deepEqual(s.documents, ["/", "/admin"]);
  assert.equal(await page.locator("script[data-cf-beacon]").count(), 0);
  const link = page.getByRole("link", { name: "查看详细统计" });
  assert.equal(await link.getAttribute("href"), "https://dash.cloudflare.com/?to=/:account/web-analytics");
  assert.equal(await link.getAttribute("target"), "_blank");
  await page.screenshot({ path: `/private/tmp/heshan-analytics-dashboard-${fallback ? "history" : "navigation"}.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: `/private/tmp/heshan-analytics-dashboard-mobile-${fallback ? "history" : "navigation"}.png`, fullPage: true });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByRole("button", { name: "退出登录" }).click(); await s.settle();
  await page.getByRole("heading", { name: "登录", exact: true }).waitFor();
  await page.getByRole("link", { name: "去注册" }).click(); await s.settle();
  assert.equal(s.scripts.length, 1, "auth documents and same-document auth routes never load beacon");
  await page.getByRole("link", { name: "去登录" }).click(); await s.settle();
  await page.locator("input[name=username]").fill(user.username);
  await page.locator("input[name=password]").fill("fixture-password");
  await page.getByRole("button", { name: "登录", exact: true }).click(); await s.settle();
  await page.getByRole("heading", { name: "聊天广场" }).waitFor();
  assert.equal(s.scripts.length, 2, "returning from login to public creates one new measured document");
  const viewPaths = s.views().map((payload) => new URL(payload.location).pathname);
  assert.deepEqual(viewPaths, ["/", "/chat", "/find", "/chat", "/find", "/chat"]);
  assert.equal(new Set(s.views().map((payload) => payload.pageloadId)).size, s.views().length);
  const serialized = JSON.stringify(s.payloads);
  for (const value of [secret, user.token, user.username, user.displayName, user.email, "fixture-password"]) assert.equal(serialized.includes(value), false);
  assert.equal(s.payloads.some((payload) => /^\/(admin|login|register)(\/|$)/.test(new URL(payload.location).pathname)), false);
  assert.deepEqual(s.errors, []);
  await s.context.close();
  console.log(`PASS official beacon SPA, privacy and route boundary (${fallback ? "History API" : "Navigation API"})`);
}

(async () => {
  const beaconPath = process.env.CLOUDFLARE_BEACON_TEST_FILE;
  assert.ok(beaconPath, "Set CLOUDFLARE_BEACON_TEST_FILE to a freshly downloaded, unmodified official beacon");
  const beacon = await fs.readFile(beaconPath, "utf8");
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    args: ["--disable-features=LocalNetworkAccessChecks"] });
  try {
    for (const base of [dev, preview]) {
      const s = await setup(browser, beacon);
      for (const path of ["/", "/chat", "/find", "/posts/1", "/admin", "/login", "/register"]) { await s.page.goto(base + path); await s.settle(); }
      assert.equal(s.scripts.length, 0); assert.equal(s.payloads.length, 0); assert.deepEqual(s.errors, []);
      await s.context.close(); console.log(`PASS localhost disabled ${base}`);
    }
    const s = await setup(browser, beacon);
    for (const path of ["/admin", "/admin/posts", "/admin/comments", "/login", "/register"]) {
      await s.page.goto(origin + path); await s.settle(); assert.equal(await s.page.locator("script[data-cf-beacon]").count(), 0);
    }
    assert.equal(s.scripts.length, 0); assert.equal(s.payloads.length, 0); assert.deepEqual(s.errors, []);
    await s.context.close(); console.log("PASS production direct excluded pages disabled");
    const publicPages = await setup(browser, beacon);
    for (const path of ["/", "/chat", "/find", "/posts/1", "/privacy"]) {
      await publicPages.page.goto(origin + path + "?email=" + secret); await publicPages.settle();
      assert.equal(await publicPages.page.locator("script[data-cf-beacon]").count(), 1);
    }
    assert.equal(publicPages.scripts.length, 5);
    assert.equal(JSON.stringify(publicPages.payloads).includes(secret), false);
    assert.deepEqual(publicPages.errors, []);
    await publicPages.context.close(); console.log("PASS production public documents enabled");
    await scenario(browser, beacon, false);
    await scenario(browser, beacon, true);
    const boundary = await setup(browser, beacon);
    await boundary.page.goto(origin + "/admin"); await boundary.settle();
    await boundary.page.getByRole("link", { name: "访问网站", exact: true }).click(); await boundary.settle();
    assert.equal(await boundary.page.locator("script[data-cf-beacon]").count(), 1);
    await boundary.page.getByRole("link", { name: "管理后台", exact: true }).click(); await boundary.settle();
    assert.equal(await boundary.page.locator("script[data-cf-beacon]").count(), 0);
    await boundary.page.goBack(); await boundary.settle();
    assert.equal(await boundary.page.locator("script[data-cf-beacon]").count(), 1);
    await boundary.page.goForward(); await boundary.settle();
    assert.equal(await boundary.page.locator("script[data-cf-beacon]").count(), 0);
    await boundary.page.goto(origin + "/register"); await boundary.settle();
    await boundary.page.locator("input[name=username]").fill(user.username);
    await boundary.page.locator("input[name=password]").fill("fixture-password");
    await boundary.page.locator("input[name=displayName]").fill(user.displayName);
    await boundary.page.getByRole("button", { name: "注册", exact: true }).click(); await boundary.settle();
    await boundary.page.getByRole("heading", { name: "聊天广场" }).waitFor();
    assert.equal(await boundary.page.locator("script[data-cf-beacon]").count(), 1);
    assert.equal(boundary.payloads.some((payload) => /^\/(admin|login|register)(\/|$)/.test(new URL(payload.location).pathname)), false);
    assert.deepEqual(boundary.errors, []);
    await boundary.context.close(); console.log("PASS cross-document back/forward and registration return");
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
