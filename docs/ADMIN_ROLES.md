# heshan.net Administrator Roles

## Current deployment warning

The default database is still `jdbc:h2:mem:tonghehui`. Restarting removes users, posts,
comments, roles and audits. No live account has been upgraded to SUPER_ADMIN by this change.
The founder initializer refuses an in-memory database. Tests use isolated synthetic accounts.

## Permissions

| Operation | USER | ADMIN | SUPER_ADMIN |
| --- | --- | --- | --- |
| Public authenticated publication | Yes | Yes | Yes |
| Dashboard, users read, post/comment moderation | No | Yes | Yes |
| Administrator list, grant/revoke ADMIN | No | No | Yes |
| Create another SUPER_ADMIN or demote founder on Web | No | No | No |

Registration always assigns USER. No profile role update, account ban, or account deletion API
exists. Do not add any such API without checking the current actor role and protected target ID.
H2 Console remains disabled and now requires SUPER_ADMIN if enabled; never expose it publicly.

SecurityConfig checks admin routes, including all HTTP methods, before public matchers. The
new controller and role service also use method authorization. The role service reloads its
actor from the database, locks the target row, validates the expected role, and commits the
new role together with the audit. A stale or repeated confirmation returns 409. Failures roll back
both changes. JWT contains a username, not an authoritative role; JwtAuthenticationFilter reloads
database authorities on every request. Revocation blocks subsequent requests using an old token.
Already authorized in-flight requests are not forcibly cancelled.

## New APIs

Both require a valid SUPER_ADMIN Bearer token.

- `GET /api/admin/administrators?page=0&size=20&search=ghost&role=ADMIN`
  uses the existing page envelope and UserItem fields. Only ADMIN and SUPER_ADMIN rows are returned.
  Role is optional; USER filter returns no records. Search matches username/displayName literally.
- `PATCH /api/admin/users/{id}/role`, body:

```json
{"role":"ADMIN","expectedRole":"USER"}
```

The reverse request is `{"role":"USER","expectedRole":"ADMIN"}`. No other transition is
accepted. Missing fields / SUPER_ADMIN as new role return 400, absent account 404,
protected target or unauthorized actor 403, stale/same-role confirmation 409.
Success returns the existing UserItem DTO, without password/hash.

## Database Changes

- `users.role` accepts SUPER_ADMIN in the existing varchar enum column; default remains USER.
- `founder_identity`: singleton `id=1`, immutable `user_id` (unique), `created_at`.
  Protection uses this stored account ID even after a username change. SUPER_ADMIN targets are
  additionally protected regardless of whether a founder row exists.
- `role_change_audit`: `id`, `actor_id`, `target_user_id`, `old_role`, `new_role`, `created_at`,
  `action` (`GRANT_ADMIN`, `REVOKE_ADMIN`, `INITIALIZE_FOUNDER`).

There are no public audit write/delete endpoints or mutable audit fields. The offline initialization
audit uses the confirmed founder ID as actor and target, distinguished by INITIALIZE_FOUNDER;
the actual server operator is accountable through private server access logs. Use least-privilege
database credentials, backups, and externally retained audit copies in production; these records
are not cryptographically tamper-proof against a database/server administrator.

Hibernate `ddl-auto=update` adds the schema locally. Production requires backups and a reviewed
schema migration. The current driver is H2 only; external database support was not added.

## One-Time Founder Initialization

This command is NOT executed by normal startup and has no HTTP endpoint. It does not reset
passwords, create accounts, promote by username alone, or grant a second SUPER_ADMIN.
Only the exact confirmed existing account ID and username `ghost` are accepted.

1. Obtain the owner's confirmation before doing anything. Choose persistent storage and migrate
   any data that must be preserved. Changing the JDBC URL does not migrate the existing memory DB.
2. On the private server, configure a persistent H2 file, for example
   `SPRING_DATASOURCE_URL=jdbc:h2:file:/absolute/private/path/heshan` plus a private database password.
   Use the same datasource credentials/path for the application and command. Do not commit secrets.
   The guard reads the actual JDBC metadata URL and only accepts `jdbc:h2:file:` in this version.
3. Have the owner register normally, then verify **both** account ID and exact username using the
   existing admin Users view/API or a private read-only database query. A public registrant claiming
   `ghost` is not proof of ownership. Independently verify the owner controls the intended account.
4. Back up the persistent database and stop the backend to release the H2 file lock. Disable the
   development admin bootstrap. Build the jar with Java 17 and `mvn clean package`.
5. Only after the owner confirms the target, run this private server command. Replace `42` in both
   places with the verified ID. The number is an example, not an account selected by this change.

```bash
export SPRING_DATASOURCE_URL=jdbc:h2:file:/absolute/private/path/heshan
export SPRING_JPA_HIBERNATE_DDL_AUTO=validate
export SPRING_JPA_SHOW_SQL=false
java -jar backend/target/backend-0.0.1-SNAPSHOT.jar \
  --initialize-founder \
  --founder-id=42 --founder-username=ghost \
  --confirm-founder-id=42 --confirm-founder-username=ghost
```

Ensure the new schema already exists before `validate`. Obtain the DB password from private server
configuration or secure shell input; it is deliberately not embedded in this example. The command
opens a non-Web context and closes after the transaction. Invalid confirmations fail without any
role change. Re-running after success fails. A singleton INSERT prevents concurrent initialization
from overwriting the protected owner; a losing transaction rolls back.
6. Restart normally without `--initialize-founder`, disable the dev profile and initializer, and
   use a private JWT signing key. Verify `/api/auth/me` reports SUPER_ADMIN for the owner.
   Normal restarts do not perform any founder authorization.

## Frontend

ADMIN and SUPER_ADMIN share daily management. `/admin/administrators` and its sidebar item
(Administrator Management) are SUPER_ADMIN-only. Users has grant/revoke icon actions; administrator
list has revoke actions, with no action for SUPER_ADMIN. Native confirmation dialogs identify ID,
username, display name and old/new role. Success refreshes rows; stale confirmations require a refresh.
403 responses trigger identity revalidation. Menu hiding is not relied on for API security.
Public homepage, chat/find menus and the shared site header show a Management link only after
`/api/auth/me` confirms ADMIN or SUPER_ADMIN. Logout hides it; cached client roles alone do not show it.

## Verification

`AdministratorIntegrationTest` covers registration injection (including ghost), USER/admin denials,
SUPER_ADMIN list/search, both levels' post/comment moderation, grants/revocations, old JWT rejection,
illegal transitions, stale/missing input, founder ID protection after rename, lack of account/audit
mutation APIs, atomic rollback when audit storage fails, and memory DB initialization refusal.
`FounderBootstrapTest` executes the offline command only against its own temporary file DB,
checks confirmation failures, saved founder identity, audit, persistence after reopen and repeat refusal.
Existing Admin v0.1 and IP location tests remain included. No live founder authorization is performed.

## Files In This Change

Backend: `TongHeHuiApplication`, `Role`, `UserRepository`, `SecurityConfig`, `AdminService`;
new `AdministratorController`, `AdministratorService`, `FounderIdentity` / repository,
`RoleChangeAudit` / repository, `FounderBootstrapCommand`, `FounderBootstrapService`;
tests `AdministratorIntegrationTest`, `FounderBootstrapTest`.

Frontend: `App.jsx`, admin `api.js`, `useAdminError.js`, `AdminRoute`, `AdminLayout`, `AdminHeader`,
`AdminSidebar`, `AdminResourcePage`, `styles/admin.css`;
new `RoleChangeDialog`, `AdminAdministratorsPage`, `tests/admin-roles.smoke.cjs`.
Public navigation: `components/AdminLink.jsx`, `components/SiteHeader.jsx`, `pages/LandingPage.jsx`,
`pages/PostsPage.jsx`, `pages/FindPeoplePage.jsx`.
Documentation: root README, `docs/README.md`, `docs/ADMIN.md`, this file.

Completed verification: Java 17 `mvn clean package` with the local MMDB test option passed
all 30 tests (no failures, errors or skips). Frontend production build and IP label unit test passed.
Isolated Playwright tests passed eight role/viewport combinations (SUPER_ADMIN, ADMIN, USER, guest
at 1440px and 390px), including confirmation/cancel, grant/revoke refresh, conflict errors, guarded
menus/routes and no document overflow. SUPER_ADMIN UI uses intercepted fixtures, not live accounts.
With Playwright available in the test environment, run `node tests/admin-roles.smoke.cjs` from frontend;
use `PLAYWRIGHT_CHANNEL=chrome` to use installed Chrome and `TEST_BASE_URL` for a different dev URL.
No Playwright dependency was added to the application itself. Screenshots are saved under `/private/tmp`.

## Known Limits

No Web creation of a second super admin, account bans/deletions, or audit browsing UI.
No migration to production SQL, tamper-proof audit infrastructure, or JWT username rename scheme.
Renaming an account invalidates its existing username-based JWT; founder ID protection still applies.
The default memory DB and development JWT key are unsuitable for formal authorization/production.
SUPER_ADMIN live UI cannot be exercised by a real owner until persistent storage and explicit
owner-confirmed initialization are completed. Never provision a live super admin merely for preview.
