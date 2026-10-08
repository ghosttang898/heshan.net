export function formatIpLocation(item) {
  if (item?.ipLocationStatus !== "RESOLVED" || !item.ipCountry) return "未知";
  const place = item.ipCity || item.ipRegion;
  return place && place !== item.ipCountry ? `${item.ipCountry} · ${place}` : item.ipCountry;
}

export const ipLocationStatusLabels = {
  UNKNOWN: "未知（历史记录）", RESOLVED: "已解析", NON_PUBLIC: "非公网地址",
  INVALID_IP: "地址无效", DATABASE_UNAVAILABLE: "数据库不可用", NOT_FOUND: "未找到",
  TIMEOUT: "查询超时", LOOKUP_FAILED: "查询失败",
};

export function formatIpLocationStatus(value) {
  return ipLocationStatusLabels[value] || ipLocationStatusLabels.UNKNOWN;
}
