# Deployment Readiness

Review date: 2026-10-11 (America/New_York). This is a local pre-release review,
not authorization or execution of a production deployment, DNS switch or founder
promotion. No VPS connection, production DB startup or Git push occurred here.

This document preserves the INITIAL review snapshot. Its Git/support/build
blockers are superseded by the completed local upgrade and validation in
[Release candidate preparation](RELEASE_CANDIDATE.md). Public cutover still
requires a new VPS trial of the upgraded image, HTTPS/Pages and offsite restore.

## Decision

The core application/database integration is ready for the next approved staging
deployment. Public production launch is NOT ready while the release gates below
remain open. Passing the integration test does not configure HTTPS, offsite
backups, monitoring or immutable release provenance.

## Evidence And Git State

The owner reports a real Ubuntu 24.04 VPS rehearsal completed with Final status
PASS, Containers stopped True and exit 0: Spring Boot, Flyway V1, Hibernate,
registration/roles, founder initialization, persistent storage and backup restore.
This review did not independently fetch those root-private reports. Archive the
actual result.json, execution/container logs, project name, image IDs and resource
snapshot privately; they must identify the candidate artifact being released.

At the start of the initial review, `git ls-remote origin refs/heads/main` and HEAD identified
`85fe677a1c31f596f7ecbb2c9fe0562a7b22d3fa` (Web Analytics). Numerous production
and test fixes were modified/untracked locally: they were NOT committed or pushed.
Do not build a release from GitHub main assuming it contains these changes.
The check request has not been treated as permission to publish an unreviewed
dirty worktree. Explicitly review/stage/commit/push the intended files separately.

Local rechecks in this review: 17 script/Compose-parser regressions, 3 backup
tests and 8 frontend tests passed; git diff --check passed. The frontend
production rebuild remained at transforming without completion for over three
minutes and was stopped; no build success or code-error cause is claimed for
that attempt. Recheck build completion before release. Backend business code
was not changed or retested with Maven in this review; the owner's successful
VPS integration report is the database/runtime evidence.

Artifacts/secrets must not be staged: target/dist/node_modules, database files,
env values, MMDB, backups, screenshots and private diagnostic reports. Ignore
rules exclude env/dumps/build output; blank .env.example files are intentionally
included. Local key-pattern review found no private keys in inspected source,
but pattern matching is not a complete secret or vulnerability audit.

## Configuration Review

| Area | Checked configuration | Remaining verification |
| --- | --- | --- |
| PostgreSQL | Named `postgres_data` volume; private internal network; no published port | Reserve `heshan_postgres_data` for the fixed production project; verify it is NEW, never reuse a test volume |
| Persistence | Default project name `heshan`; init only on an empty volume | Freeze project name/path; never change `-p` expecting the same data; never use `down -v` |
| Backend | PostgreSQL/Flyway enabled, Hibernate validate, H2/dev-bootstrap forbidden | Use immutable reviewed AMD64 image and prod profile |
| Restart | DB/backend/proxy `unless-stopped` | Verify restart after Docker/host restart in staging; manually stopped services remain stopped |
| Health | TCP PG readiness, DB-aware backend health, proxy health | Alerts required: unhealthy alone does not invoke the restart policy |
| Security | Non-root/read-only backend, cap_drop ALL, no-new-privileges, quoted 64 MiB tmpfs | Retain restrictions and verify mounted file permissions |
| Secrets | DB/JWT env injection, blank credential examples, prod guard rejects default/weak JWT | Generate independent production credentials outside Git; mode-0600 files in private server directory |
| Ingress | Backend has no host port; proxy only `127.0.0.1:8080` | This is private HTTP, NOT a finished public HTTPS API |
| Logging | Each service json-file 10m x 3; no public access log/IP/query/JWT data | Health/backup/low-disk/OOM alerts and private diagnostics |
| Resources | DB 384 MiB, backend 768 MiB, proxy 64 MiB, optional backup job 128 MiB | Real representative load and concurrent backup memory verification |
| Founder | USER registration; generic confirmed ID/name offline command; singleton/audit; no ADMIN promotion to SUPER_ADMIN | Verify owner's actual ghost account ID/control and obtain explicit one-time authorization |

Production secrets are not hardcoded. A publicly known development JWT default
remains in the H2 development configuration; the production configuration has
no fallback and its startup guard explicitly rejects that default. Test fixtures
and the public Cloudflare beacon identifier are not production API credentials.
Never print expanded Compose config or container Env output into shared logs.

## 2 GiB Capacity

Always-on container caps sum to 1216 MiB; with the optional backup job, 1344 MiB.
These are limits, not measured consumption. The OS/Docker, filesystem cache and
other services still need headroom. The reported integration success establishes
basic viability on the 1-vCPU/2-GiB/1-GiB-swap VPS, not production throughput.
Keep the 5-connection app pool and 20-connection PostgreSQL limit initially.
Do not run Maven/frontend builds on this VPS. A lightweight runtime image build
from a locally compiled JAR may be separately approved; never overlap it with
production traffic/backup without capacity review. Swap does not replace RAM.

Pause backend writes and stop the normal backend BEFORE the offline founder
JVM runs; do not run a second 768-MiB backend concurrently. Avoid overlapping
backup, restore rehearsal and image builds. Confirm actual networks do not
overlap `172.30.10.0/24`, gateway is `172.30.10.1`, and loopback 8080 is unused.

## Dependency Support Gate

The initial POM used Spring Boot 3.3.12. The official announcement states that
3.3.13 ended OSS support for the 3.3.x line on 2025-06-19. Before public exposure,
approve migration to a currently supported Java-17-compatible release and run
the full regression/VPS test again, or verify an applicable commercial support
and patched-dependency plan. Do not assume the historical recommendation in that
announcement is the current supported-version list. No framework upgrade is
performed by this review. Inspect image/JDK/PostgreSQL/Nginx/frontend dependencies
as well; no complete CVE scan has been run here.

Subsequent action: upgraded to stable Boot 4.1.1/Java 17 and validated all backend
tests including real local PostgreSQL/prod-profile HTTP. See RELEASE_CANDIDATE.md
for exact dependency versions and supported migration changes. This resolves
the framework support gate, not the remaining public-ingress/backup gates.

Source: https://spring.io/blog/2025/06/19/spring-boot-3-3-13-available-now/

## Pre-Deployment Checklist

- [x] Owner confirms no H2 data retention; new empty production PostgreSQL only.
- [x] Owner reports real isolated PostgreSQL integration PASS and stopped containers.
- [x] Review private DB ports, volume, security caps, prod guard and founder mechanism.
- [ ] Archive root-private successful test evidence and candidate image IDs/checksums.
- [ ] Review all intended local changes; commit/push to GitHub main; verify remote SHA.
- [ ] Build release from that exact commit; record JAR checksum, AMD64 image ID/digest and external image digests; do not release a mutable pg-test tag.
- [ ] Complete dependency support/CVE review and approve supported versions.
- [ ] Generate private production DB/admin/JWT credentials; no test credential reuse.
- [ ] Confirm production project/name/volume, server paths, disk/memory and network/port conflicts; preserve all old/test data.
- [ ] Confirm staging hostname, exact HTTPS CORS origins and Pages API build URL.
- [ ] Rehearse the production proxy/HTTPS arrangement in staging, including untrusted forwarded-header spoofing and healthchecks.
- [ ] Approve TLS certificate/ingress and Cloudflare Pages configuration; public-domain/DNS changes require separate explicit authorization.
- [ ] Select/approve external backup storage, budget, least-privilege rclone credentials, encryption and retention (local 7 days/offsite 30 days).
- [ ] Execute real offsite upload/download/restore rehearsal; local pg_dump restore does NOT verify external storage.
- [ ] Install daily backup scheduling and private failure alerts only when deployment is approved; ensure server UTC scheduling is intentional.
- [ ] Validate Pages refresh/public posts/comments, authentication, admin authorization and Analytics exclusions against staging API.
- [ ] Complete a fresh frontend production build from the reviewed release commit; investigate a stalled build rather than using an unverified artifact.
- [ ] Register ghost as USER in the correct production DB; privately verify ID/control before any role initialization.
- [ ] Perform representative load, host/Docker restart and low-memory/OOM monitoring checks.
- [ ] Record rollback artifacts and obtain a final owner go/no-go before enabling public access or switching the old site.

## Founder Configuration And Confirmation

`deploy/.env.example` contains `FOUNDER_USERNAME=ghost` as non-secret deployment
metadata ONLY. Compose normal startup and registration do not consume it for
authorization. Operators copy the approved value into the offline command;
do not source an env file containing production passwords just to read a name.
No user ID is guessed or supplied as a default. The service accepts any exact
verified owner name, not a hardcoded ghost rule.

Future procedure (NOT executed): owner registers, independently verifies
ownership + ID/name, backs up DB, pauses backend writes, and explicitly confirms
both ID and username. Invoke the command with the SAME approved prod env/image
and fixed project. Its four arguments are:

```text
--founder-id=<verified ID>
--founder-username=<approved FOUNDER_USERNAME>
--confirm-founder-id=<independently confirmed same ID>
--confirm-founder-username=<independently confirmed same username>
```

After one-time success, restart backend without initialization flags, log in
again, verify /api/auth/me is SUPER_ADMIN, singleton founder identity and audit.
No account has been promoted by this readiness check. See PRODUCTION.md for
the command template; its sample ID 42 must never be executed as an assumed ID.

## Rollback Plan

1. Before each release, privately preserve the previous image IDs/digests, JAR,
   Compose/proxy config, env version, frontend artifact/deployment ID and actual
   project/volume names. Record who can approve rollback. Keep the legacy site
   and its DNS/resources untouched throughout pre-release preparation.
2. Before each migration or founder initialization, create a checksummed DB dump,
   complete approved offsite upload, and verify restore usability. V1 uses a new
   empty DB; later migrations must remain compatible with the preceding app
   where possible. Never modify applied Flyway checksums or run clean/repair as
   an automatic recovery step.
3. If the first staging/production candidate fails BEFORE public cutover, keep
   traffic on the unchanged legacy site. Stop only the new backend/proxy by
   their exact production project if needed; retain DB/volume/reports. Correct
   config and re-test, never wipe data to obtain a green startup.
4. If a subsequent application release fails and the schema is compatible,
   restore the recorded prior backend image/config and prior Pages deployment.
   Confirm health, login, role enforcement, posts/comments and new-data integrity.
   A previous image alone is not a rollback for an incompatible DB migration.
5. For schema corruption/incompatibility, pause writes and preserve the failed
   DB/volume. Restore a verified backup into a NEW isolated volume/database,
   validate schema/rows/audit/roles and explicitly approve the switch. Disclose
   the backup timestamp and potential loss of writes after that point. Do not
   overwrite the original database or silently accept that data loss.
6. For leaked credentials, separately rotate DB/JWT/backup credentials using an
   approved procedure; env-file edits alone do not rotate initialized PG roles.
   JWT rotation invalidates sessions. Rolling back an image does not repair a
   compromised secret or revoke founder authorization safely.
7. Any future DNS reversal, public proxy change or deletion needs its own owner
   approval. No such action is authorized or executed by this document.

Open approvals: reviewed Git publication, dependency support path, release image
provenance, private staging/HTTPS approach, external backup provider/retention,
production env/volume paths, founder ownership and final public cutover.
