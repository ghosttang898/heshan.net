# heshan.net Admin v0.1

The management workspace at `/admin` adds dashboard statistics, post/comment moderation,
and user search. The public Chinese/Heshan community pages keep their existing routes and behavior.

## Development administrator

No administrator credentials are included in Git. Ordinary registration always creates `USER`.
An administrator can be created by explicitly enabling the server initializer in the `dev` profile:

```bash
cd backend
export SPRING_PROFILES_ACTIVE=dev
export APP_ADMIN_BOOTSTRAP_ENABLED=true
export APP_ADMIN_BOOTSTRAP_USERNAME=local-admin
read -s 'APP_ADMIN_BOOTSTRAP_PASSWORD?Choose a development admin password (at least 12 characters): '
export APP_ADMIN_BOOTSTRAP_PASSWORD
mvn spring-boot:run
```

The `read` example is for macOS zsh. On other shells, set the environment variables using that
shell's secure input mechanism. Java 17 must be active. Sign in at `/login` with the chosen credentials,
then visit `/admin` (or visit `/admin` first to return there after login).

The initializer only runs with both `dev` and `APP_ADMIN_BOOTSTRAP_ENABLED=true`.
It creates a new account and hashes the supplied password with BCrypt. If that username already
belongs to `USER`, startup fails instead of promoting the account. An existing `ADMIN` is left unchanged,
including its password. Turn bootstrap off after account creation for a persistent deployment.
H2 is currently in-memory: restarting removes users, posts, and comments, so the development
initializer must run again if you need an administrator after a restart.

Do not expose the development profile publicly. For a real deployment, use a trusted server-side
provisioning process for roles, a private JWT signing key via `APP_JWT_SECRET`, and durable database storage.
The current local JWT default is a development key. H2 Console is disabled by default and its routes
require SUPER_ADMIN if deliberately enabled; it is not needed for this workflow. Never enable it publicly.

## Schema additions

- `users.role`: `USER`, `ADMIN`, or `SUPER_ADMIN`, defaults to `USER`.
- `posts.status`, `comments.status`: `PUBLISHED`, `HIDDEN`, or `DELETED`, defaults to `PUBLISHED`.
- Existing post `author_id` and comment `user_id` relationships are preserved.

String enum columns have SQL defaults so existing rows receive `USER` / `PUBLISHED` when Hibernate
adds columns in the development H2 schema. Keep backups and use a reviewed migration when introducing
a persistent production database; `ddl-auto=update` is only the present development workflow.

Public creation ignores supplied moderation status and assigns `PUBLISHED` server-side. The post author
comes from the authenticated account. Registration never accepts role assignments.

## Authentication and authorization

`POST /api/auth/login` and `POST /api/auth/register` retain their existing fields and now return
`role` alongside `token`, `username`, and `displayName`.

`GET /api/auth/me` requires a valid Bearer JWT and returns `id`, `username`, `displayName`, `role`.
No password or hash is returned. JWT identifies the username; Spring Security reloads that account's
current role from the database on every request. A demoted administrator's existing token loses
admin access without waiting for expiration.

Daily `/api/admin/**` paths and methods allow `ROLE_ADMIN` or `ROLE_SUPER_ADMIN`: missing/invalid authentication receives
401, a signed-in `USER` receives 403. React verifies `/api/auth/me` for the admin route and redirects
guests to login; this is only UX. Editing local storage cannot bypass backend authorization.
Administrator list and role assignment are SUPER_ADMIN-only. See [Role management](ADMIN_ROLES.md)
for protected founder identity, role audit schema, transition rules and offline initialization.

## Admin APIs

All requests below use `Authorization: Bearer <token>`.

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/admin/dashboard` | Totals, today's counts, five recent posts and users |
| GET | `/api/admin/posts` | Paginated posts; `search`, `type`, `status` filters |
| GET | `/api/admin/posts/{id}` | Full post, including hidden/deleted content |
| PATCH | `/api/admin/posts/{id}/status` | Set moderation status |
| GET | `/api/admin/comments` | Paginated comments; `search`, `status` filters |
| GET | `/api/admin/comments/{id}` | Full comment and parent post reference |
| PATCH | `/api/admin/comments/{id}/status` | Set moderation status |
| GET | `/api/admin/users` | Paginated users; `search`, `role` filters |
| GET | `/api/admin/users/{id}` | User details and post/comment counts |
| GET | `/api/admin/administrators` | SUPER_ADMIN-only paginated administrator list |
| PATCH | `/api/admin/users/{id}/role` | SUPER_ADMIN-only USER / ADMIN transition with expectedRole |

List parameters: `page` is zero-based (default 0), `size` defaults to 20 and must be 1–100.
Results are ordered by `createdAt DESC, id DESC`. The response is:

```json
{"content": [], "page": 0, "size": 20, "totalElements": 0, "totalPages": 0}
```

Search is trimmed, case-insensitive literal substring matching. Post search checks title/content;
comment search checks content; user search checks username/displayName. `%` and `_` are literal,
not user-provided SQL wildcards. Invalid filters, missing status, and invalid pagination return 400;
nonexistent records return 404. Post filters use `CHAT` / `FIND_PERSON`; role filters use `USER` / `ADMIN` / `SUPER_ADMIN`.

Post/comment status request:

```json
{"status": "HIDDEN"}
```

Use `PUBLISHED` to restore or `DELETED` to soft delete. Restoration is allowed for hidden or
soft-deleted items. No moderation operation physically deletes a row. Public post lists and details
only expose `PUBLISHED`; comments on hidden/deleted posts cannot be fetched or added. Public comment
lists only expose `PUBLISHED` comments. Hiding a parent does not change its children's statuses.

Admin post records include full content, author `{id, username, displayName}`, type, status, createdAt,
and the existing find-person fields. Comment records include full content, author (null for anonymous),
postId, postTitle, status, createdAt. User records contain id, username, displayName, role, createdAt,
postCount, commentCount, never a password. User counts and dashboard totals include all statuses;
anonymous comments count in comment totals but are not assigned to a user. Today's counts cover the
server-local calendar day `[00:00, next day 00:00)`; set the JVM/server timezone deliberately when deploying.

## Frontend

- `/admin`: six statistics and recent posts/users.
- `/admin/posts`: search, type/status filters, pagination, full detail and moderation.
- `/admin/comments`: search, status filter, pagination, full detail and moderation.
- `/admin/users`: username/displayName search, role filter, pagination, user detail.
- `/admin/administrators`: SUPER_ADMIN-only list and revocation; grants reuse the Users page search.

The independent admin layout has a sidebar, account header, compact tables, responsive navigation,
loading/empty/error states, and native modal detail panels with explicit moderation confirmation.
Filters and pagination live in the URL. `lucide-react` is the only added frontend dependency, used
for familiar navigation, search, pagination, refresh, and detail icons. Frontend changes use the
existing Axios Bearer interceptor. Token expiration redirects admin users to login.

Post/comment tables and details also expose publication country, region, city and IP location
query status. These read-only snapshots contain no original IP and are unchanged by moderation.
See [IP location](IP_LOCATION.md) for the additive fields, database setup and trusted proxy rules.

## Verification

```bash
cd backend
mvn test
mvn package
cd ../frontend
npm ci
npm run build
```

`AdminIntegrationTest` exercises real JWT login with Spring Security and H2 through MockMvc:
401/403, registration role injection, role reload, dashboard totals/day boundaries, pagination,
search/filters, moderation and restore, retained soft-deleted rows, authenticated post authors,
anonymous/signed-in comments, and bootstrap refusal to promote ordinary accounts.

Manual UI checks should include guest redirect, ordinary-user 403, admin navigation/search,
detail confirmation, mobile table scrolling, and the original home/register/login/chat/find/detail flow.

### Completed verification

- `mvn -B package`: passed; 8 integration tests, no failures or errors.
- `npm run build`: passed.
- Browser checks passed for guest login redirect, USER access denied, ADMIN login/dashboard,
  post type filtering and detail, hiding/restoring a post, soft-deleting a comment, user search/detail,
  and author post/comment totals. Hidden posts and deleted comments disappeared from the public UI.
- The original home (backend status `ok`), registration, login, CHAT and FIND_PERSON creation,
  nickname/location/year-text filtering, post detail, and signed-in comment creation were checked.
- Desktop and 390px-wide admin layouts were visually checked; the mobile document had no
  horizontal overflow. Wide tables scroll within their own workspace.
- Initial local Vite module loading stalled during first dependency/Babel loading; after retry,
  the unchanged development configuration served source modules normally. Build preview also worked.
- Installing the icon dependency reported 10 npm audit findings (4 moderate, 6 high) in the
  dependency tree. Dependency upgrades are a separate follow-up; this is not a production-security clearance.

## Scope and limitations

This version does not include reports, content-moderation audit logs, moderators, notifications,
settings, bulk actions, OAuth, or charts. Role editing now has transactional audit records;
content moderation remains last-write-wins and has no audit history yet.
H2 memory storage and the development JWT default remain local-development limitations.
