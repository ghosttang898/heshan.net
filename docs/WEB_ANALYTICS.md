# heshan.net Cloudflare Web Analytics

## Integration

The React 18 / BrowserRouter frontend manually embeds Cloudflare's unmodified official
`https://static.cloudflareinsights.com/beacon.min.js` with `type=module` and the site's
public beacon token. This token identifies the analytics site; it is NOT a Cloudflare API
credential. No account API Token, API integration, backend changes or database tables are added.

The loader runs once outside React StrictMode effects. It requires a Vite production build,
HTTPS, and hostname exactly `heshan.net` or `www.heshan.net`. All localhost, 127.0.0.1, IPv6
loopback, development builds, staging and other hostnames are disabled. The production bundle
still contains the public token, but local production previews do not execute the beacon.

An explicit pathname allowlist covers `/`, `/chat`, `/find`, numeric `/posts/:id`, and `/privacy`.
Login, registration, all admin paths, and unknown paths fail closed. Add future public routes
to this allowlist deliberately.

Cloudflare automatically measures SPA navigation via Soft Navigations, Navigation API or
History API hooks. No useLocation pageview effect, manual event, custom ingestion POST, or
extra script per public route is used. Script deduplication also checks existing beacon tags.
Performance reports and pageviews are different event types; do not count every RUM POST as a PV.

Sources:
- [Official SPA behavior](https://developers.cloudflare.com/web-analytics/get-started/web-analytics-spa/)
- [Official FAQ, manual installation, privacy and CSP](https://developers.cloudflare.com/web-analytics/faq/)
- [Collection and privacy](https://developers.cloudflare.com/speed/observatory/rum-beacon/)

## Route Exclusion: Important Limitation And Alternative

The manual beacon has no documented per-route pause/unload API. Removing a script element after
execution does not remove its event listeners. Cloudflare's edge Rules are available only for
proxied sites and govern incoming page responses, not React Router's in-document transitions:
[official Rules](https://developers.cloudflare.com/web-analytics/configuration-options/rules/).
Conditional initial loading alone is therefore NOT sufficient to exclude private SPA routes.

The implemented alternative isolates document lifetimes. `createAnalyticsRouterWindow` uses
BrowserRouter's window option and a narrowly scoped History facade. Public-to-public navigation
is delegated to the real History object, including Cloudflare's existing hooks. Crossing between
a measured public route and an unmeasured route uses `location.assign` or `location.replace`
BEFORE invoking those hooks. The new auth/admin document never loads the beacon; returning to
a public route loads it once in a new document. Auth-to-admin transitions remain SPA navigations.
React Router Link, Navigate and useNavigate all go through the same boundary. Existing admin
login redirect state remains within the unmeasured document and is preserved.

This intentionally adds a full page load at the public/auth/admin boundary in production only.
Public route transitions remain client-side; development behavior is unchanged. History back/forward
within public routes remains SPA; crossing a boundary traverses separate documents. New tabs and
ordinary document links naturally receive the same initial loading guard.
The previous public document may flush its public page's final performance report when leaving
for admin/login; that is NOT a pageview of the destination excluded page.

Do not bypass this boundary using direct window.history writes in future application code.
Use React Router navigation, or a normal full-document link. Do not implement an undocumented
beacon event API or intercept all fetch/XHR/sendBeacon requests globally.

## Privacy

Application auth/storage/form data is never passed to analytics. The beacon does not use our
Axios client, Authorization interceptor, JWT, account names, emails, post text or comment text.
Cloudflare documents that it does not access cookies, localStorage or other browser storage.
The current official beacon removes query parameters, fragments and URL credentials from page
and referrer URL fields before sending measurements. Browser tests check the actual official
payloads using deliberately planted JWT, username, email and sensitive-query markers.

The HTML referrer policy is `origin`, so outbound requests and document transitions do not carry
the current path/query as HTTP Referer. This also limits detailed internal referrer attribution.
No sensitive values should be placed in URL path segments; post routes are numeric IDs.
The official script is remotely maintained and cannot safely be version-pinned/SRI-pinned under
Cloudflare's documented manual installation. Retest the current script before production changes;
do not mistake this for a permanent guarantee about future third-party code.

The public `/privacy` page includes the provider and purpose notice. Browser/device/performance
information is processed by Cloudflare. Blocking extensions, CSP, regional settings, script/network
failure and delayed final-page reports can reduce counts. Beacon failure does not block the app.

## Dashboard

`/admin` has a Website Traffic section headed Cloudflare Web Analytics and a View Detailed Analytics
link. It opens [Cloudflare Web Analytics](https://dash.cloudflare.com/?to=/:account/web-analytics)
in a new tab with noopener/noreferrer. Cloudflare sign-in/account selection may be required.
There are no fabricated PV/UV totals or charts and no Cloudflare account API credential in the UI.

## Owner's Manual Steps

1. In Cloudflare Web Analytics, confirm this public beacon token belongs to the heshan.net site and
   its hostname configuration accepts heshan.net and your chosen www hostname. Do not use an API Token.
2. Use manual installation. Disable automatic Web Analytics snippet injection for this site if it is
   currently enabled (also check RUM/Observatory/Pages automatic injection if applicable). Do not
   paste a second script into the HTML. Automatic edge injection can defeat excluded/local guards,
   and removing a DOM script after it executes cannot repair this. This repository cannot change
   your account settings; exclusion is contingent on there being no independently injected beacon.
3. If production uses CSP, preserve existing directives and allow the script origin
   `https://static.cloudflareinsights.com` under script-src, and `https://cloudflareinsights.com`
   under connect-src for manual reporting. Test in Report-Only first; do not weaken CSP generally.
4. When you choose to deploy separately, retain the existing SPA fallback to index.html for direct
   `/chat`, `/find`, `/posts/:id`, `/login`, `/register`, and `/admin/**` document requests. It is
   especially necessary for the new production document boundary. No server/DNS change is made here.
5. In production DevTools, confirm one beacon per public document, none in admin/login/register;
   test public-to-private and private-to-public links and browser history. Inspect RUM payloads for
   URL sanitization. Leave a public page and allow time for Cloudflare's dashboard to update.

No DigitalOcean, GoDaddy, DNS, deployment, commit or push action is part of this integration.

## Verification Commands

```bash
cd frontend
npm run build
node --test src/analytics.test.js src/ipLocation.test.js
```

For browser tests, start the existing dev server and a local production preview on port 5174.
Have Playwright and Chrome available in the test environment (not added as runtime dependencies),
download the current unmodified official script into a temporary file, then run:

```bash
curl -fsSL https://static.cloudflareinsights.com/beacon.min.js -o /tmp/cloudflare-beacon-test.js
PLAYWRIGHT_CHANNEL=chrome \
  CLOUDFLARE_BEACON_TEST_FILE=/tmp/cloudflare-beacon-test.js \
  node tests/analytics.smoke.cjs
```

TEST_DEV_URL and TEST_PREVIEW_URL can override local URLs. The test maps production HTTPS requests
to the local build, serves the unchanged official script, mocks application APIs and intercepts ALL
analytics requests. It never submits measurements to Cloudflare. Test-only Chrome local-network
permission settings allow this mapping; no security setting of the user's browser is changed.
Checks cover local dev and production preview, direct excluded pages, SPA navigation/back/forward,
granting no extra pageview IDs, document boundaries, login return, real payload privacy and console
errors. Both Navigation API and fallback History API environments are exercised.

Completed locally on 2026-10-08: `npm run build` passed; five Node tests passed (four analytics
policies plus the existing IP label test). All seven browser analytics groups passed against the
current unmodified official beacon (JS version 2026.10.0), with zero captured console/runtime
errors. Cross-document back/forward, login and registration returns, desktop/mobile Dashboard,
and URL/storage-secret markers were checked. The existing eight administrator role/viewport
smoke scenarios also passed. All Cloudflare reports were intercepted; production account ingestion
and real dashboard totals still require the owner's post-deployment check.

## Changed Files

- `frontend/src/analytics.js`, `frontend/src/analytics.test.js`
- `frontend/src/main.jsx`, `frontend/index.html`
- `frontend/src/admin/pages/AdminDashboardPage.jsx`, `frontend/src/admin/styles/admin.css`
- `frontend/src/pages/PrivacyPage.jsx`
- `frontend/tests/analytics.smoke.cjs`
- `docs/WEB_ANALYTICS.md`, `docs/README.md`
