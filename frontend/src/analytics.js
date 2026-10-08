export const CLOUDFLARE_BEACON_URL = "https://static.cloudflareinsights.com/beacon.min.js";
export const CLOUDFLARE_ANALYTICS_DASHBOARD = "https://dash.cloudflare.com/?to=/:account/web-analytics";
const BEACON_TOKEN = "51e38dcc9b204689b9caa1fdea20a4ba";
const SCRIPT_ID = "heshan-cloudflare-analytics";

export function isAnalyticsEnvironment(production, location) {
  return production && location.protocol === "https:"
    && ["heshan.net", "www.heshan.net"].includes(location.hostname);
}

export function isPublicAnalyticsPath(pathname) {
  return pathname === "/" || /^\/(chat|find|privacy)\/?$/.test(pathname)
    || /^\/posts\/\d+\/?$/.test(pathname);
}

export function loadCloudflareAnalytics(browser, production) {
  if (!isAnalyticsEnvironment(production, browser.location)
      || !isPublicAnalyticsPath(browser.location.pathname)) return;
  const document = browser.document;
  if (document.getElementById(SCRIPT_ID) || document.querySelector("script[data-cf-beacon]")) return;
  const script = document.createElement("script");
  script.id = SCRIPT_ID;
  script.type = "module";
  script.src = CLOUDFLARE_BEACON_URL;
  script.setAttribute("data-cf-beacon", JSON.stringify({ token: BEACON_TOKEN }));
  script.referrerPolicy = "origin";
  document.head.appendChild(script);
}

export function createAnalyticsRouterWindow(browser, production) {
  if (!isAnalyticsEnvironment(production, browser.location)) return browser;
  const measuredDocument = isPublicAnalyticsPath(browser.location.pathname);
  const history = new Proxy(browser.history, {
    get(target, property) {
      if (property === "pushState" || property === "replaceState") {
        return (state, unused, url) => {
          if (url != null) {
            const destination = new URL(url, browser.location.href);
            if (destination.origin === browser.location.origin
                && isPublicAnalyticsPath(destination.pathname) !== measuredDocument) {
              // Beacon has no route-level teardown. Change documents BEFORE calling its History hooks.
              const method = property === "replaceState" ? "replace" : "assign";
              browser.location[method](destination.href);
              return;
            }
          }
          return target[property].call(target, state, unused, url);
        };
      }
      const value = Reflect.get(target, property, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
  return new Proxy(browser, {
    get(target, property) {
      if (property === "history") return history;
      const value = Reflect.get(target, property, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}
