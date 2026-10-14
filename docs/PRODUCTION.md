# Production Preparation

> Historical preparation reference. V1 is now live; start with
> [V1 handover](V1_HANDOVER.md) for actual revisions and remaining work.
> Founder initialization is complete: never rerun the example below.
> Pages, B2/rclone, offsite automation and new controllers are paused under MVP.
> Use the current production Compose wrapper with the GeoIP overlay; template
> commands and obsolete paths below are not instructions to redeploy production.

This change prepares local code only. No VPS connection, DNS change, database
deployment, owner promotion, Pages deployment or Git push has been performed.
The currently online legacy website is not touched.

For the latest pre-release review, including the owner's successful VPS test
report, remaining gates and rollback checklist, see [Deployment readiness](DEPLOYMENT_READINESS.md).
The historical local Testcontainers skip described below does not invalidate
the separately completed real VPS rehearsal.

## Database And Migrations

The five entities are User, Post, Comment, FounderIdentity and RoleChangeAudit.
All five repositories use portable JPA/specifications/JPQL; there is no H2-only
repository SQL. Their production tables are `users`, `posts`, `comments`,
`founder_identity` and `role_change_audit`.

`backend/src/main/resources/db/migration/postgresql/V1__initial_schema.sql`
creates an EMPTY PostgreSQL 16 schema, including identity BIGINT IDs, varchar
enum fields, microsecond timestamps without time zone, content length limits,
nullable anonymous comment authors and nullable historical IP-location fields.
No raw IP column is introduced. Username/founder uniqueness, foreign keys,
singleton founder ID and a partial unique SUPER_ADMIN index are enforced.
Indexes cover public status/time ordering, authors, post comments and audit
actors/targets. Username uniqueness remains case-sensitive as before.

Flyway runs once and checks its version/checksum on subsequent starts; V1 is
not a script to manually execute repeatedly. Do not edit an applied migration;
add V2, V3, etc. DDL is transactional on PostgreSQL. There is no DROP/TRUNCATE,
seed account, baseline-on-migrate, automatic clean or repair. Existing nonempty
schemas without Flyway history are rejected for manual review, not adopted.

Default local H2 config is retained, with Flyway disabled. `prod` instead uses
PostgreSQL + Flyway + Hibernate `validate`; startup guard runs before datasource
initialization and rejects H2, schema update, unsafe Flyway settings, missing/
default/weak JWT environment secrets, development bootstrap and unsafe CORS.

The owner has confirmed no old H2 data needs preservation: the selected release
starts with a new empty PostgreSQL database. This does not authorize deleting
any legacy server or test resources. The following transfer guidance is optional
only if that decision changes.

**Changing DB_URL does not move H2 data.** Do not stop a running memory database
that holds data to preserve. Before a data move, identify the actual source,
export all five tables securely with consistent IDs, bcrypt password hashes,
roles, founder identity, audits and timestamps; import only into a new isolated
migrated PostgreSQL instance in dependency order; then reset identity sequences
above imported maxima and compare counts, constraints, selected records and
login/moderation behavior. H2 SQL exports are not directly PostgreSQL SQL.
Do not baseline/import an unknown legacy schema or infer author/IP values.
This change does not implement or execute an H2-to-PostgreSQL data importer.
That requires a separately reviewed source export and owner confirmation.

The isolated PostgreSQL integration test checks initial migration, Hibernate
validation for all entities, repeated migration preserving inserted data,
founder confirmation/one-time initialization/audit and second-super-admin refusal.
The upgraded tests require local Docker and fail rather than silently skip when
it is unavailable. Run them successfully before deployment. H2 security/file-persistence
tests do not substitute for this PostgreSQL test or a real data-transfer rehearsal.

## Secrets And Permissions

Production variables: DB_URL, DB_USER, DB_PASSWORD, APP_JWT_SECRET,
APP_CORS_ALLOWED_ORIGINS. Compose derives database values from the protected
server-local env file. JWT must come from the actual process environment;
an overridden `app.jwt.secret` cannot silently substitute a different key.
Generate independent random database passwords and a JWT key of at least 32
random bytes (Base64 encoding recommended). Do not print secrets into terminal
recordings, commands, tickets, Git, build arguments or VITE variables.

Use a mode-0600 server-local env file and mode-0600 rclone configuration. Only
root/authorized operators should access Docker: inspect/config output can reveal
environment credentials. Use `docker compose config --quiet`, not rendered
config in public logs. `.env.example` contains empty secret fields, no credentials.
Env files, database dumps, H2 files, build output and MMDB files are ignored.

On a fresh PostgreSQL volume, `deploy/postgres-init.sh` uses psql getenv and safe
identifier/literal quoting to create a NOSUPERUSER/NOCREATEDB/NOCREATEROLE app
role. A separate postgres admin password is NOT given to the backend. The app
role owns its database and may apply Flyway migrations; stricter separate runtime
and migrator roles can be added later. Server/DB administrators can still alter
audit records; the existing audit is not tamper-proof against them.
Init scripts only run on a fresh volume. Changing env passwords does not rotate
an existing database's passwords, and failed initialization must be reviewed
without deleting the volume. Never use `docker compose down -v`.

USER/ADMIN/SUPER_ADMIN, DB-reloaded JWT authorities, backend role checks and
audits are preserved. Normal registration is always USER, even for `ghost`.
Founder initialization now accepts PostgreSQL or persistent H2 file storage;
memory databases remain rejected. Production adds DB-level singleton checks.

### Founder Initialization (Not Executed)

First privately verify ownership AND the existing account's ID/username/role;
username `ghost` alone proves nothing. Back up PostgreSQL, obtain explicit owner
confirmation, pause backend writes and invoke the existing offline command using
the same prod env/image. `42` below is an example, never an automatically selected ID:

```bash
docker compose --env-file /etc/heshan/app.env -f /opt/heshan/deploy/compose.yml \
  run --rm --no-deps backend --initialize-founder \
  --founder-id=42 --founder-username=ghost \
  --confirm-founder-id=42 --confirm-founder-username=ghost
```

It opens no web listener and performs role change, singleton insert and audit
in one transaction. Repetition/invalid confirmations fail. No public endpoint
or normal-startup username promotion exists. Re-enable normal service separately.

## Compose And Resource Budget

`deploy/compose.yml` is a starting point, NOT an automatically deployed stack.
PostgreSQL uses a named persistent volume, an internal network and no published
5432 port. Backend publishes no port. Only the proxy is loopback-published at
127.0.0.1:8080 for staging/private host reverse-proxy access. It does not serve
or replace an existing website. Changing public ingress is a separate task.

Caps: PostgreSQL 384 MiB (64 MiB shared buffers, 20 connections), backend
768 MiB (320 MiB heap, bounded native pools and 5 DB connections), Nginx
64 MiB, optional offsite job 128 MiB. Services have CPU/PID limits, healthchecks
and json-file 10m x 3 logging. The app uses a non-root read-only filesystem.
The GeoIP reader is memory-mapped instead of copying the whole DB into heap.
Allow OS/page-cache headroom and verify real load/OOM behavior on the 2 GiB VPS.
Healthchecks mark unhealthy; Docker restart policies restart exited processes,
not containers merely marked unhealthy. Monitor unhealthy/backup failures.

Image builds must happen on Mac/CI, not the VPS. Example (after local tests):

```bash
cd backend
JAVA_HOME=/path/to/jdk17 mvn clean package
docker buildx build --platform linux/amd64 -t <approved-registry>/heshan-backend:<commit> .
```

Choose the image registry/transfer method and confirm costs before pushing images.
Record/pin reviewed immutable digests for backend, PostgreSQL, proxy and rclone
before formal release; current external image tags are templates, not immutable
deployment locks. Never perform a PostgreSQL major upgrade by changing its image
tag over an existing volume. PostgreSQL 16 is the selected initial major.

The static network 172.30.10.0/24 must not overlap existing host/Docker networks.
Backend trusts only proxy 172.30.10.10. Nginx trusts the specified bridge gateway
172.30.10.1 for forwarding from a future host TLS proxy, then overwrites XFF to
one resolved address. The host TLS proxy must overwrite client-supplied XFF;
do not unconditionally trust Cloudflare/client forwarding. Review actual peers
and verify spoofed-header behavior in staging before enabling public ingress.

HTTPS termination/certificates and any host reverse-proxy config are deliberately
not deployed here. The loopback HTTP proxy is NOT a complete public TLS setup.
Confirm certificate method, host ingress, Cloudflare proxy mode and staging host
before any DNS/server changes. `/actuator/health` is internal to the backend;
only `/api/` is proxied publicly. Health response details are disabled.

For public IP-location results, select the optional `deploy/compose.geoip.yml`
override together with the base Compose file and set GEOIP_DATABASE_FILE to an
approved server-local City MMDB. Its bind mount is read-only and refuses missing
paths. Without this override/database, publication still works but location is
unknown. Confirm provider license/attribution and monthly atomic updates before
enabling it; never commit the file or replace it in place while it is mapped.

## Daily Backups And Restore

`docs/scripts/backup-postgresql.sh` runs on the host using its local Docker socket.
It exports a custom-format pg_dump (compression level 3) with the app role, writes
only a new protected backup file/checksum, and invokes the optional offsite
rclone job. It never passes database passwords in argv. Upload failure fails
the job and keeps local backups. Upload success alone is not enough to authorize
retention pruning; the script now performs no deletion at all. The proposed
7-day local/30-day offsite policy and per-object verification gates are described
in `docs/STAGING_BACKUP_AUTOMATION.md`. Historical backups are not auto-managed.
Partial failed dumps remain for operator inspection, not blind removal.

Select an **external** storage provider/bucket (not another directory/container
on the VPS), least-privilege credentials restricted to its backup prefix, TLS,
server-side encryption and an approved budget. Configure rclone and BACKUP_REMOTE
privately. Set an offsite lifecycle policy of 30 days; consider versioning/immutable
retention if supported. Configure that policy only after owner approval. This
change has not contacted any storage provider or verified real offsite transfer.

Do not install the former direct cron recipe. Follow the approval gates in
`docs/STAGING_BACKUP_AUTOMATION.md` for a resource-monitored supervisor and
systemd timer with individually verified offsite receipts before activation.

The proposed schedule uses UTC and uploads dumps and checksums; arrange private failure alerts,
monitor age/size/transfer results and verify a download from a different machine.
Do not log credentials. Backup secrecy matters: dumps contain password hashes,
community content, roles and audits. Env/JWT/rclone secrets need separate secure
recovery storage, not inclusion in public/database dump directories.

For monthly restore rehearsal, verify the offsite dump and checksum on a trusted
machine, then obtain approval for a fully isolated target and a same-snapshot
reference. Never restore into the real database merely to test a backup.

The former one-argument `test-restore-postgresql.sh` command is no longer supported.
The hardened runner currently accepts **Staging backups only**, requires explicit
approval, a checksum-bound reference and confirmed owner ID/username, and retains
its stopped temporary container and protected reports. See
[the isolated Staging restore plan](STAGING_ISOLATED_RESTORE.md).
It is not an automatic production restore tool. Production rehearsal, database
login grants and application login/moderation need a separately approved plan;
the dump intentionally excludes ACL/ownership.

## Cloudflare Pages

React/Vite is static and suitable for Pages. Build root: `frontend`, command:
`npm ci && npm test && npm run build`, output: `dist`. Set the PUBLIC build variable
VITE_API_BASE_URL=https://api.heshan.net/api for the eventual production frontend;
use a separate staging HTTPS API origin for a test Pages project/pages.dev URL.
Backend CORS must contain exact allowed frontend HTTPS origins, not wildcard.
VITE variables are public, never secret. An unset variable retains the local
Vite `/api` proxy convention; it is not a valid cross-host Pages API setup.

`frontend/public/_redirects` rewrites only known application routes to index.html
and is copied to dist; it does not use `/*`, which could rewrite JS/CSS assets.
Pages' native SPA fallback covers other paths when no root 404.html exists.
Refresh `/chat`, `/find`, `/posts/:id`, `/admin`, `/login` and `/register`
on the real test Pages deployment before approval. Do not add a top-level 404.html
that disables Pages' own SPA default. No Pages Functions are introduced.

Analytics remains unchanged: HTTPS heshan.net/www only, allowed public paths only,
and document boundaries on crossing admin/auth routes. `/admin/**`, `/login`,
`/register` are excluded; pages.dev/staging/localhost are intentionally not measured.
Tests cover exclusions and duplicate-script prevention. Do not enable a second
Cloudflare auto-injected beacon or put personal data in URL path segments.
The official live beacon payload and actual Pages SPA behavior need staging
browser verification; unit tests/build alone do not verify live hosting.

## Release Gates And Rollback

Before server deployment obtain confirmation for staging endpoints, persistent
database name/volume, source data to preserve, random credentials delivery,
registry/image digests, subnet/port conflicts, HTTPS ingress, offsite provider/
cost/retention, optional GeoIP database and independently verified founder ID/ownership. This is not
authorization to modify DNS or promote an account.

Run the Testcontainers PostgreSQL test with Docker available, build the amd64
image, verify database init/app startup/health and resource usage in isolated
staging, rehearse offsite restore and verify admin/JWT/CORS/IP forwarding and
Pages refresh/analytics behavior. Do not switch the legacy domain beforehand.

Record prior image/env/Compose config and back up the database before each
migration. Initial migration failures roll back transactional DDL; later
migrations must remain backward-compatible with the previous app image where
possible. Roll back app images only against compatible schema. Destructive schema
recovery means restoring to a NEW isolated volume and reviewing it before any
switch, never deleting/overwriting the original volume or automatic Flyway clean.

## Files In This Preparation

- `.gitignore`
- `backend/pom.xml`, `backend/Dockerfile`, `backend/.dockerignore`
- `backend/src/main/resources/application.properties`, `application-prod.properties`
- `backend/src/main/resources/META-INF/spring.factories`
- `backend/src/main/resources/db/migration/postgresql/V1__initial_schema.sql`
- `backend/src/main/java/net/tonghehui/backend/security/ProductionEnvironmentGuard.java`
- `backend/src/main/java/net/tonghehui/backend/security/SecurityConfig.java`, `JwtService.java`
- `backend/src/main/java/net/tonghehui/backend/admin/FounderBootstrapService.java`
- `backend/src/main/java/net/tonghehui/backend/geolocation/IpGeolocationService.java`
- `backend/src/test/java/net/tonghehui/backend/security/ProductionEnvironmentGuardTest.java`, `CorsIntegrationTest.java`
- `backend/src/test/java/net/tonghehui/backend/admin/PostgresMigrationIntegrationTest.java`
- `deploy/compose.yml`, `deploy/nginx.conf`, `deploy/postgres-init.sh`, `deploy/.env.example`
- `deploy/compose.geoip.yml`
- `frontend/package.json`, `frontend/.env.example`, `frontend/public/_redirects`
- `frontend/src/api.js`, `apiBaseUrl.js`, `apiBaseUrl.test.js`
- `frontend/src/pagesDeployment.test.js`
- `frontend/tests/analytics.smoke.cjs` (cross-origin API fixtures only)
- `docs/scripts/backup-postgresql.sh`, `test_backup_postgresql.py`, `test-restore-postgresql.sh`
- `docs/PRODUCTION.md`, `docs/README.md`, `docs/ADMIN_ROLES.md`, `docs/IP_LOCATION.md`

Previously generated Docker installation/logging scripts are left unchanged.
Dependencies are selected by the existing Spring Boot dependency management;
the subsequent supported Boot 4.1.1 upgrade and real local PostgreSQL regression
are documented in RELEASE_CANDIDATE.md. Re-test the new SHA image on the VPS
before exposing production services; the previous VPS image is not this upgrade.

Official references:

- https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes
- https://www.postgresql.org/docs/16/app-psql.html
- https://developers.cloudflare.com/pages/configuration/serving-pages/
- https://developers.cloudflare.com/pages/configuration/redirects/
