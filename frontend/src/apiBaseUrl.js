export function resolveApiBaseUrl(value, production) {
  const base = value?.trim() || "/api";
  if (base === "/api") return base;
  const url = new URL(base);
  if (url.username || url.password || url.search || url.hash
      || !["http:", "https:"].includes(url.protocol)
      || (production && url.protocol !== "https:")
      || !/^\/api\/?$/.test(url.pathname)) {
    throw new Error("API base URL must be an HTTPS /api endpoint without credentials or query parameters");
  }
  return `${url.origin}/api`;
}
