import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom/server.js";
import { build } from "esbuild";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

let components;
let directory;
before(async () => {
  globalThis.localStorage = { getItem: () => null };
  const paths = ["pages/RegisterPage", "pages/PostsPage", "pages/FindPeoplePage",
    "components/PostList", "components/FindPersonPostList", "components/CommentList"];
  const result = await build({
    stdin: { contents: paths.map((path, index) => `export {default as C${index}} from './${path}.jsx';`).join("\n"),
      resolveDir: fileURLToPath(new URL("./", import.meta.url)), loader: "js" },
    bundle: true, platform: "node", format: "esm", jsx: "automatic", write: false,
    external: ["react", "react-dom", "react-router-dom", "axios"], loader: { ".png": "dataurl" },
    define: { "import.meta.env.PROD": "false", "import.meta.env.VITE_API_BASE_URL": "undefined" },
  });
  directory = mkdtempSync(fileURLToPath(new URL("../node_modules/.ui-tests-", import.meta.url)));
  const file = join(directory, "components.mjs");
  writeFileSync(file, result.outputFiles[0].text);
  const bundled = await import(pathToFileURL(file));
  components = Object.fromEntries(paths.map((path, index) => [`/src/${path}.jsx`, bundled[`C${index}`]]));
});
after(() => {
  if (directory) rmSync(directory, { recursive: true });
  delete globalThis.localStorage;
});

async function render(path, props = {}) {
  const Component = components[path];
  return renderToStaticMarkup(React.createElement(StaticRouter, { location: "/" }, React.createElement(Component, props)));
}

test("registration includes shared website navigation", async () => {
  const html = await render("/src/pages/RegisterPage.jsx");
  assert.match(html, /aria-label="网站导航"/);
  assert.match(html, /href="\/chat"/);
  assert.match(html, /href="\/find"/);
});

test("post and find pages initially render status rather than an empty list", async () => {
  for (const [path, props] of [["/src/pages/PostsPage.jsx", { type: "CHAT" }], ["/src/pages/FindPeoplePage.jsx", {}]]) {
    const html = await render(path, props);
    assert.match(html, /role="status"/);
    assert.doesNotMatch(html, /还没有聊天帖子|没有匹配的寻人帖子/);
  }
});

test("loading lists suppress empty and stale content; ready lists still have empty states", async () => {
  for (const path of ["/src/components/PostList.jsx", "/src/components/FindPersonPostList.jsx"]) {
    const loading = await render(path, { posts: [], emptyText: "EMPTY_FIXTURE", loading: true });
    assert.match(loading, /role="status"/);
    assert.doesNotMatch(loading, /EMPTY_FIXTURE/);
    const stale = await render(path, { posts: [{ id: 1, title: "STALE_FIXTURE" }], emptyText: "EMPTY_FIXTURE", loading: true });
    assert.doesNotMatch(stale, /STALE_FIXTURE/);
    const ready = await render(path, { posts: [], emptyText: "EMPTY_FIXTURE", loading: false });
    assert.match(ready, /EMPTY_FIXTURE/);
    assert.doesNotMatch(ready, /role="status"/);
  }
});

test("comments distinguish loading from an actually empty result", async () => {
  const loading = await render("/src/components/CommentList.jsx", { comments: [], loading: true });
  assert.match(loading, /role="status"/);
  assert.doesNotMatch(loading, /还没有评论/);
  const ready = await render("/src/components/CommentList.jsx", { comments: [], loading: false });
  assert.match(ready, /还没有评论/);
});
