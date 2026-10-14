# MVP Input Validation

This change adds application validation only. It requires no schema migration,
database reset, account initialization or permission change.

## API Limits

Invalid fields return HTTP 400 before encoding a password or saving content.
Production continues to suppress internal exception details. The frontend shows
specific local validation errors and safe status-based request errors, never raw
server messages, SQL or credentials.

| Endpoint | Required fields | Limits |
| --- | --- | --- |
| POST /api/auth/register | username, displayName, password | Trimmed username/displayName: 255 characters; password: 72 UTF-8 bytes |
| POST /api/auth/login | username, password | Trimmed username: 255 characters; password: 72 UTF-8 bytes |
| POST /api/posts | title, content, type | Title: 255; content: 4000; optional nickname/location/yearRange: 255 characters each |
| POST /api/posts/{id}/comments | content | 2000 characters |

Blank required fields are rejected. Passwords are never trimmed or silently
truncated. Character limits on the backend count Unicode code points, matching
PostgreSQL character semantics. Browser maxLength uses UTF-16 units and can be
more restrictive for emoji; the API remains authoritative.

Post types remain CHAT and FIND_PERSON. Historical free-text year ranges remain
valid; no new year format restriction is imposed. New accounts remain USER.
Post author, status, ID and IP location remain server-controlled. Anonymous
comments remain supported, as explicitly confirmed by the owner.

## Verification and Release

Run backend `mvn test`, frontend `npm test` and `npm run build`. Regression tests
cover invalid/boundary input, multibyte passwords, anonymous comments and attempted
registration role elevation. Submission failures preserve form drafts and re-enable
the submit button.

These changes and the existing year-search fix are local until an approved Staging
update. That update must preserve the PostgreSQL Volume, TLS/configuration, loopback
ingress and test accounts; rebuild only application artifacts. Do not include paused
B2/backup-framework work in the business release. Use the existing update procedure,
with a verified backup and previous application image available for rollback.

No VPS, DNS, production service, scheduler or administrator account is changed by
local validation tests. Staging/browser acceptance must be reported separately.

## Local Results (2026-10-13)

- Backend Maven: 50 tests, 49 passed, 1 skipped, 0 failures/errors. New input
  integration tests: 10 passed. FounderBootstrapTest: 3 passed. The skipped test
  needs an optional GeoIP database fixture (`geoip.test.database`).
- Existing local PostgreSQL 16 Testcontainers integration: passed, including
  Flyway/Hibernate and administrator safety checks. No VPS database was accessed.
- Frontend: 23 tests passed, including the existing year-range regression tests.
- Production build: exit 0. Due to macOS cloud placeholders in node_modules,
  final build used an isolated copy of the current frontend with cached dependencies
  whose package-lock SHA256 exactly matches this repository. Only the unused,
  unreferenced legacy logo-heshan.png was excluded from that copy.
- Playwright/Chrome: 1440px desktop and 390px mobile mocked form checks passed.
  Registration blank-input errors and post submission failure/draft retention were
  checked; no horizontal overflow or page script errors were observed. Anonymous
  comment identity, submission error display, draft retention and button recovery
  also passed at both widths using mocked responses.
- Staging deployment, real-network browser acceptance and production launch:
  NOT TESTED in this round. No code was committed or pushed.

Next approval should cover only a backed-up Staging application update and its
functional acceptance. Keep anonymous comments enabled. Formal launch remains a
separate decision.
