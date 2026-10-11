# Release Candidate Preparation

This preparation is local only. The existing public site, DNS, VPS and production
database have not been changed. Production/test preparation was first committed
as `a90a86e`; the upgrade and final validation form the following release commit.
Resolve its exact SHA with `git rev-parse HEAD` and compare with GitHub main after
push. Do not use a mutable pg-test image as the formal release artifact.

## Supported Backend And Compatibility

The backend now uses Spring Boot 4.1.1 with Java 17. This was selected instead
of 3.5.x because that line's final OSS release was 3.5.16. No preview/snapshot
framework is selected. Boot's BOM manages the coordinated versions:

| Component | Version |
| --- | --- |
| Spring Boot | 4.1.1 |
| Spring Security | 7.1.1 |
| Hibernate ORM | 7.4.5.Final |
| Flyway | 12.4.0 |
| PostgreSQL JDBC | 42.7.13 |
| Testcontainers | 2.0.5 |
| HTTP Jackson | 3.1.5 |

Boot 4's focused Web MVC/Flyway/test starters and package names are used.
MockBean/SpyBean were replaced by Spring Test's MockitoBean/MockitoSpyBean.
DaoAuthenticationProvider receives the existing UserDetailsService through its
constructor. The production EnvironmentPostProcessor now uses Boot 4's supported
interface and factory key; unsafe configuration still fails before DB startup.
JJWT uses its own Jackson 2 adapter; the application's HTTP/test mapper is Jackson
3. Both coexist under BOM management and login/token tests verify compatibility.

FounderBootstrapService, AdministratorService, AuthService and Flyway V1 are
unchanged from the validated preparation commit. Registration always USER;
confirmed owner ID/name, persistent DB, singleton/audit and rejection of a second
SUPER_ADMIN remain intact. No actual founder authorization is performed here.

Local full Java-17 package validation passed 39 tests, 0 failures/errors/skips.
Real PostgreSQL 16 tests cover initial/repeat Flyway migration, Hibernate validate,
non-superuser app DB role, data preservation, founder confirmation and singleton.
A new full prod-profile test auto-migrates a fresh DB, starts HTTP on loopback,
registers with injected role ignored, checks USER denial, initializes only the
confirmed synthetic owner, checks current DB authority with an old token and
restarts against the same DB. PostgreSQL test ports bind only 127.0.0.1 and the
test container is limited to 384 MiB. PostgreSQL tests require Docker now; they
do NOT silently skip an unavailable daemon.

Official references:

- https://docs.spring.io/spring-boot/system-requirements.html
- https://spring.io/blog/2026/08/20/spring-boot-4-1-1-available-now/
- https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide

## Frontend Reproducible Build

React 18/Vite/React Router and Analytics runtime are retained. The stalled local
build was waiting on filesystem reads: existing node_modules had iCloud dataless
files. npm cache inspection also found root-owned cache files. No existing
dependencies/cache or user dev server were deleted/reconfigured to obtain a pass.

The same source and lockfile were copied to an unsynced private temporary directory
and built with fresh dependencies under Node 24. `npm ci`, eight frontend tests
and `npm run build` passed; build exit code was 0. Repeat with a local Docker
daemon (script rejects remote Docker endpoints):

```bash
bash docs/scripts/verify-frontend-build.sh
```

The script only copies public source/build config; it does not copy .env files,
existing node_modules, credentials, backend data or private logs. Output remains
in its printed workspace/dist. Node image ID is recorded; for repeatable releases
set NODE_BUILD_IMAGE to a reviewed digest. On Cloudflare Pages use Node 24,
fresh `npm ci`, `npm test`, `npm run build`, root frontend and output dist.
VITE_API_BASE_URL is public and must point to the approved HTTPS staging API
until final cutover approval, then https://api.heshan.net/api.

Production-built UI browser checks passed all eight admin/role/viewport cases;
real official beacon tests passed localhost exclusion, admin/login/register
exclusion, public pages, SPA/back/forward, auth boundary navigation and payload
privacy under Navigation API and History API. All API/metrics were intercepted;
no real accounts or public analytics events were created. Browser fixtures now
include CORS for the separate API origin. Screenshots/beacon/build outputs remain
outside Git. Actual Pages hosting/HTTPS staging still requires separate approval.

## Git SHA Image Versioning

After committing and pushing all validated changes, use a CLEAN checkout of the
same full SHA for the JAR and image. Rebuild locally/CI, never Maven on the VPS:

```bash
git status --porcelain
REV=$(git rev-parse HEAD)
# Stop if the checkout is dirty. Use Java 17 and a local Docker daemon.
JAVA_HOME=/path/to/jdk17 mvn -f backend/pom.xml -B package
docker buildx build --platform linux/amd64 --load \
  --build-arg VCS_REF="$REV" -t "heshan-backend:$REV" backend
shasum -a 256 backend/target/backend-0.0.1-SNAPSHOT.jar
docker image inspect --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}' "heshan-backend:$REV"
```

Dockerfile records org.opencontainers.image.revision; its unversioned-test
default is for experiments only. Refuse a release whose revision label does not
match REV. Record source SHA, JAR checksum, image ID/platform and Docker archive
checksum together. Never retag a different binary over an existing SHA tag.

For a no-registry transfer, export that exact image with docker save, verify the
archive checksum before/after ordinary-user SCP, and let the owner interactively
sudo docker load on the new VPS. This is a FUTURE procedure, not executed here.
Alternatively approve a registry and pin the resulting repository digest. Set
BACKEND_IMAGE to the full SHA tag (or approved digest) in a private env file;
record/pin PostgreSQL/Nginx/rclone/base-image digests as release metadata too.

The VPS already tested an older framework image. Do not reuse that old pg-test
image for this upgrade: run the isolated VPS rehearsal again with the new SHA
artifact AFTER separate authorization, before any production traffic cutover.

## Production Boundaries And Budget

PostgreSQL remains on an internal network and persistent named volume; neither
DB nor backend has a published port. 127.0.0.1:8080 is the proxy's ONLY host bind,
not a direct backend listener. Preserve the production project name and volume;
do not use test volumes, change PostgreSQL major version casually or run down -v.

DB 384 MiB + backend 768 MiB + proxy 64 MiB = 1216 MiB always-on caps; optional
backup job adds 128 MiB. Backend heap is 320 MiB, metaspace 128 MiB, bounded native
pools; PG shared buffers 64 MiB, max connections 20, app pool 5. Leave room for
Ubuntu/Docker/cache, monitor OOM/swap/latency and avoid overlapping builds, founder
JVM and restore jobs. This is suitable for a controlled 2-GiB staging trial, not
a measured production-throughput promise. Keep non-root/read-only/capability
restrictions, quoted 64-MiB tmpfs and json-file 10m x 3 logging.

## Nginx And HTTPS Plan

deploy/nginx.conf stays private HTTP ingress. The NEW disabled
deploy/nginx-api-https.conf.example is a FUTURE host-Nginx template only: API
server name, HTTP-to-HTTPS redirect, TLS 1.2/1.3, approved certificate paths,
API-only proxy to 127.0.0.1:8080 and overwritten forwarding headers. It neither
requests certificates, changes DNS nor installs itself. Do not overwrite any
existing virtual host or enable it without staging and owner approval.
The template passed local `nginx -t` in an isolated no-network container using
a temporary self-signed test certificate outside Git. This is syntax validation,
NOT a real trusted certificate, public HTTPS or DNS verification.

First review current host services/ports/network ranges, select staging hostname
and certificate issuance method and validate the complete proxy chain. Backend
trusts only the configured internal proxy. If Cloudflare proxies the API, first
review its current trusted CIDRs and real-IP header handling; never trust headers
from arbitrary clients. The template conservatively uses the direct socket IP.
Review forwarded scheme before introducing redirects/secure cookies; the current
inner proxy uses its HTTP scheme and authentication uses bearer tokens, not
forwarded-protocol-derived cookies. Do not use Flexible TLS as a substitute for
origin HTTPS. No public TLS/DNS/Pages configuration is activated by this change.

## Backup And Release Gates

Daily pg_dump custom format, checksums, private local files, 7-day local retention
and offsite rclone upload are prepared. Configure an APPROVED external storage
provider/least-privilege credentials/encryption/budget, 30-day offsite retention,
daily UTC scheduler and private failure alerts. Retention pruning occurs only
after offsite upload succeeds. Real external upload/download/restore has not been
validated; local restored fixtures do not prove disaster recovery off the VPS.
The full local deployment-script regression suite passed 44 tests, including
mount normalization, failure logs, swap and backup safety; shell syntax and
git diff whitespace checks also passed.

ghost is non-secret deployment metadata in the env example, not a source-code
authorization rule. Register USER, verify ownership and both ID/name, back up DB,
pause writes/stop backend, obtain explicit authorization and run the protected
one-time command with the SAME production image/env. Restart/login and verify
SUPER_ADMIN plus founder identity/audit. Never guess ID or grant by username.

Ready next: an owner-approved isolated VPS trial of the upgraded SHA artifact.
NOT ready for public cutover until the new VPS trial, complete HTTPS/Pages/API
staging, offsite restore, resource monitoring and final owner approval pass.
Retain the existing rollback plan in DEPLOYMENT_READINESS.md: prior image/env/
frontend artifacts; schema-compatible image rollback; otherwise restore to a NEW
volume after write freeze, preserve old data and approve any loss/switch.
