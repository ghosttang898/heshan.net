import test from "node:test";
import assert from "node:assert/strict";
import { formatIpLocation, formatIpLocationStatus } from "./ipLocation.js";

test("public location formatting and historical fallback", () => {
  assert.equal(formatIpLocation({ ipLocationStatus: "RESOLVED", ipCountry: "美国", ipCity: "Philadelphia", ipRegion: "Pennsylvania" }), "美国 · Philadelphia");
  assert.equal(formatIpLocation({ ipLocationStatus: "RESOLVED", ipCountry: "中国", ipRegion: "广东" }), "中国 · 广东");
  assert.equal(formatIpLocation({ ipLocationStatus: "RESOLVED", ipCountry: "美国" }), "美国");
  for (const item of [undefined, {}, { ipLocationStatus: "TIMEOUT" }, { ipLocationStatus: "UNKNOWN", ipCountry: "美国" }]) {
    assert.equal(formatIpLocation(item), "未知");
  }
  assert.equal(formatIpLocationStatus("NON_PUBLIC"), "非公网地址");
  assert.equal(formatIpLocationStatus(null), "未知（历史记录）");
});
