const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const base = process.env.TEST_BASE_URL || "http://127.0.0.1:5173";

async function scenario(browser, role, viewport) {
  const context = await browser.newContext({ viewport });
  const owner = { id: 1, username: "fixture-owner", displayName: "测试所有者", role, createdAt: "2026-10-01T12:00:00", postCount: 0, commentCount: 0 };
  const rows = [owner, { ...owner, id: 2, username: "fixture-member", displayName: "测试成员", role: "USER" },
    { ...owner, id: 3, username: "fixture-admin", displayName: "测试管理员", role: "ADMIN" }];
  const requests = [];
  let conflict = false;
  if (role) await context.addInitScript((auth) => localStorage.setItem("tonghehui_auth", JSON.stringify(auth)), { ...owner, role: "SUPER_ADMIN", token: "isolated-ui-fixture" });
  // Every API is intercepted: these UI tests never authorize or mutate a live website account.
  await context.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    let result;
    let status = 200;
    if (url.pathname === "/api/auth/me") result = owner;
    else if (/\/api\/admin\/users\/\d+\/role$/.test(url.pathname)) {
      requests.push(request.postDataJSON());
      if (conflict) { status = 409; result = {}; }
      else {
        const row = rows.find((row) => row.id === Number(url.pathname.split("/")[4]));
        row.role = request.postDataJSON().role; result = row;
      }
    } else if (["/api/admin/users", "/api/admin/administrators"].includes(url.pathname)) {
      let items = rows.filter((row) => url.pathname.endsWith("/users") || row.role !== "USER");
      if (url.searchParams.get("search")) items = items.filter((row) => row.username.includes(url.searchParams.get("search")));
      if (url.searchParams.get("role")) items = items.filter((row) => row.role === url.searchParams.get("role"));
      result = { content: items, page: 0, size: 20, totalElements: items.length, totalPages: 1 };
    } else if (/\/api\/admin\/users\/\d+$/.test(url.pathname)) result = rows.find((row) => row.id === Number(url.pathname.split("/")[4]));
    else { status = 404; result = {}; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(result) });
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const path of ["/", "/chat", "/find", "/posts/1"]) {
    await page.goto(base + path);
    await page.waitForLoadState("networkidle");
    const link = page.getByRole("link", { name: "管理后台", exact: true });
    const allowed = ["ADMIN", "SUPER_ADMIN"].includes(role);
    assert.equal(await link.count(), allowed ? 1 : 0);
    if (allowed) assert.equal(await link.getAttribute("href"), "/admin");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    if (path === "/chat" && role === "ADMIN") await page.screenshot({ path: `/private/tmp/heshan-chat-admin-link-${viewport.width}.png`, fullPage: true });
  }
  await page.goto(base + (role === "SUPER_ADMIN" ? "/admin/administrators" : "/admin/users"));
  if (!role) {
    await page.getByRole("heading", { name: "登录" }).waitFor();
    assert.equal(new URL(page.url()).pathname, "/login");
  } else if (role === "USER") {
    await page.getByRole("heading", { name: "403 · 无访问权限" }).waitFor();
  } else {
    await page.getByRole("cell", { name: "fixture-admin", exact: true }).waitFor();
    assert.equal(await page.getByRole("link", { name: "管理员管理", exact: true }).count(), role === "SUPER_ADMIN" ? 1 : 0);
    if (role === "ADMIN") {
      assert.equal(await page.getByRole("button", { name: /的管理员权限/ }).count(), 0);
      await page.goto(base + "/admin/administrators");
      await page.getByRole("heading", { name: "403 · 无访问权限" }).waitFor();
    } else {
      assert.equal(await page.getByRole("cell", { name: "fixture-member", exact: true }).count(), 0);
      assert.equal(await page.getByRole("button", { name: "撤销 fixture-owner 的管理员权限" }).count(), 0);
      await page.screenshot({ path: `/private/tmp/heshan-administrators-${viewport.width}.png`, fullPage: true });
      await page.getByRole("link", { name: "前往用户管理" }).click();
      await page.getByRole("button", { name: "授权 fixture-member 的管理员权限" }).click();
      await page.getByRole("dialog").waitFor();
      await page.getByRole("button", { name: "取消", exact: true }).click();
      assert.equal(requests.length, 0);
      await page.getByRole("button", { name: "授权 fixture-member 的管理员权限" }).click();
      await page.screenshot({ path: `/private/tmp/heshan-role-dialog-${viewport.width}.png`, fullPage: true });
      await page.getByRole("button", { name: "确认变更" }).click();
      await page.getByRole("button", { name: "撤销 fixture-member 的管理员权限" }).waitFor();
      assert.deepEqual(requests[0], { role: "ADMIN", expectedRole: "USER" });
      await page.getByRole("link", { name: "管理员管理", exact: true }).click();
      await page.getByRole("button", { name: "撤销 fixture-member 的管理员权限" }).click();
      await page.getByRole("button", { name: "确认变更" }).click();
      await page.getByRole("dialog").waitFor({ state: "hidden" });
      await page.getByRole("status").filter({ hasText: "USER" }).waitFor();
      assert.equal(await page.getByRole("cell", { name: "fixture-member", exact: true }).count(), 0);
      assert.deepEqual(requests[1], { role: "USER", expectedRole: "ADMIN" });
      conflict = true;
      await page.getByRole("button", { name: "撤销 fixture-admin 的管理员权限" }).click();
      await page.getByRole("button", { name: "确认变更" }).click();
      await page.getByRole("alert").filter({ hasText: "角色已变化" }).waitFor();
      assert.equal(await page.getByRole("button", { name: "确认变更" }).isDisabled(), true);
      await page.getByRole("button", { name: "取消", exact: true }).click();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      const overlap = await page.locator(".admin-sidebar nav a").evaluateAll((links) => links.some((link) => link.scrollWidth > link.clientWidth));
      assert.equal(overlap, false);
    }
    await page.goto(base + "/chat");
    await page.getByRole("link", { name: "管理后台", exact: true }).waitFor();
    await page.getByRole("button", { name: "退出登录", exact: true }).click();
    await page.getByRole("link", { name: "管理后台", exact: true }).waitFor({ state: "hidden" });
  }
  assert.deepEqual(errors, []);
  await context.close();
  console.log(`PASS ${role || "guest"} ${viewport.width}px`);
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
  try {
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      for (const role of ["SUPER_ADMIN", "ADMIN", "USER", null]) await scenario(browser, role, viewport);
    }
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
