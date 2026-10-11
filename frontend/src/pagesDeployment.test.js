import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

test("Pages refresh rules target routes without rewriting static assets", () => {
  const publicDir = new URL("../public/", import.meta.url);
  const rules = readFileSync(new URL("_redirects", publicDir), "utf8").trim().split("\n")
    .map((line) => line.trim().split(/\s+/));
  assert.equal(existsSync(new URL("404.html", publicDir)), false);
  assert.equal(rules.some(([source]) => source === "/*" || source.startsWith("/assets")), false);
  for (const path of ["/chat", "/find", "/privacy", "/login", "/register", "/posts/*", "/admin", "/admin/*"]) {
    assert.ok(rules.some(([source, destination, status]) => source === path && destination === "/index.html" && status === "200"));
  }
});
