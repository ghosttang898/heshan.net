import test from "node:test";
import assert from "node:assert/strict";
import { validateFields, validatePost, validateRegistration, submissionError } from "./formValidation.js";

test("registration rejects blanks and overlong identity fields", () => {
  const valid = { username: "member", displayName: "同乡", password: "local-test-password" };
  assert.equal(validateRegistration(valid), "");
  for (const field of ["username", "displayName", "password"]) {
    assert.notEqual(validateRegistration({ ...valid, [field]: "   " }), "");
  }
  assert.notEqual(validateRegistration({ ...valid, username: "a".repeat(256) }), "");
  assert.notEqual(validateRegistration({ ...valid, displayName: "名".repeat(256) }), "");
});

test("BCrypt password boundary uses UTF-8 bytes without trimming", () => {
  const valid = { username: "member", displayName: "同乡" };
  assert.equal(validateRegistration({ ...valid, password: "中".repeat(24) }), "");
  assert.notEqual(validateRegistration({ ...valid, password: "中".repeat(25) }), "");
  assert.notEqual(validateRegistration({ ...valid, password: "a".repeat(72) + " " }), "");
});

test("posts validate required content and optional legacy free-text fields", () => {
  const valid = { title: "寻找旧友", content: "留言", yearRange: "小学时期" };
  assert.equal(validatePost(valid), "");
  assert.notEqual(validatePost({ ...valid, title: "\n " }), "");
  assert.notEqual(validatePost({ ...valid, content: " " }), "");
  for (const field of ["title", "nickname", "location", "yearRange"]) {
    assert.notEqual(validatePost({ ...valid, [field]: "a".repeat(256) }), "");
  }
  assert.equal(validatePost({ ...valid, content: "中".repeat(4000) }), "");
  assert.notEqual(validatePost({ ...valid, content: "中".repeat(4001) }), "");
});

test("comments accept the exact boundary and reject empty/overlong input", () => {
  const rules = [["content", "评论", 2000, true]];
  assert.equal(validateFields({ content: "中".repeat(2000) }, rules), "");
  assert.notEqual(validateFields({ content: "中".repeat(2001) }, rules), "");
  assert.notEqual(validateFields({ content: "\n" }, rules), "");
});

test("submission errors are safe and do not echo server internals", () => {
  for (const status of [400, 401, 403, 404, 409, 500]) {
    const result = submissionError({ response: { status, data: { message: "private database secret" } } }, "稍后重试");
    assert.ok(result);
    assert.ok(!result.includes("secret"));
  }
  assert.match(submissionError({}, "fallback"), /网络/);
});
