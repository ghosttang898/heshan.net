# VPS Release Rehearsal: 5710a89

## Scope And Current Evidence

Application revision: `5710a891cd1be771e1a26f15ec5fc7fb622aeaed`.
The application was freshly cloned from GitHub into an unsynced private Mac
directory, checked out at that exact revision and compiled with Java 17 using
Maven clean package. All 39 tests passed with no failures, errors or skips,
including real local PostgreSQL 16. No application source was changed.

The local AMD64 image is
`heshan-backend:5710a891cd1be771e1a26f15ec5fc7fb622aeaed`.
Its revision label matches the approved commit. Docker's containerd image ID is
`sha256:1bb63c062d3a8194ba24d45fc0a5712a8548f933152f6ea88f6d7e231d27105c`.
The importer accepts only cryptographically verified config/manifest/index IDs
for this archive, covering both classic and Engine 29 containerd stores.

Only test tooling was extended locally: configurable synthetic founder name,
source/version checks, retained container port checks and multi-phase resource
snapshots. The 50 deployment-script regression tests and Bash syntax checks
passed. These tooling changes are not committed or pushed and do not change the
application revision inside the image.

SSH Key login succeeded. Read-only unprivileged VPS results: x86_64,
1967 MiB total RAM, 1527 MiB available, approximately 42 GiB free root disk,
1 GiB active Swap. That preparation originally stopped at interactive sudo.
The owner subsequently reported this approved artifact's VPS rehearsal PASS,
containers_stopped true and exit code 0. Its raw server report was not re-read
in the later staging-preparation task, which makes no VPS connection. Treat
this as owner-supplied historical evidence, NOT a pass for the new staging config.

## Prepared Bundle

Mac archive: `/private/tmp/heshan-release-5710a89/vps-release-test-v2.tar.gz`.
Archive SHA256:
`d1a701046603d29a02a72cb889d07d9637b67ab8cbca838e8b90e1067485c4fe`.
VPS upload directory: `/var/tmp/heshan-release-upload-2bmh9IuW`.
The bundle contains only the exported backend image, reviewed test scripts,
PostgreSQL initialization script, source revision and checksum manifest.
No SSH key, real database credential, JWT secret, database or backup is included.
Test passwords are generated only at execution in a root-private workspace.

## Owner's Interactive Command

After upload/extraction/checksum verification is confirmed, run in the Mac
terminal. Enter sudo password only at the terminal's hidden prompt:

```bash
ssh -t -i ~/.ssh/id_ed25519 heshan@165.232.156.104 \
  'sudo bash /var/tmp/heshan-release-upload-2bmh9IuW/docs/scripts/run-vps-release-test.sh /var/tmp/heshan-release-upload-2bmh9IuW 5710a891cd1be771e1a26f15ec5fc7fb622aeaed ghost'
```

The script first copies only approved files to a fresh root-private directory,
validates checksums, lists Docker versions/containers/networks/volumes/logging,
and verifies memory, Swap and disk. Any running container, less than 1300 MiB
available RAM, less than 4 GiB free disk, wrong architecture/revision, or a
conflicting existing SHA image tag aborts. No existing service is stopped.
Then it loads ONLY this SHA image, uses the existing AMD64 PostgreSQL 16 image
(pulls official postgres:16-bookworm only if absent), and executes the test wrapper.
No Maven build runs on the VPS, and the old pg-test backend image is never used.

## Isolated Checks And Reports

The wrapper chooses a random independent `heshan-it-*` Compose project and
creates only its own internal network and named test volume. No service publishes
a host port, including founder and restore command containers. PostgreSQL is
limited to 384 MiB / 0.35 CPU and the backend to 768 MiB / 0.60 CPU.

The synthetic `ghost` registers as USER even when a SUPER_ADMIN field is injected.
Only after verifying the freshly created ID does this test invoke the protected
one-time founder command. It verifies wrong confirmation and repeated command
rejection, ADMIN delegation/revocation, founder protection and current DB role
enforcement with an old JWT. This affects ONLY the isolated database, never a
real founder or existing database. Change the last command argument to test a
different username; application code does not match usernames to assign roles.

Checks include PostgreSQL's actual server version, empty initial schema, Flyway
V1, Hibernate validate and Spring Boot 4.1.1 startup, HTTP registration/login,
permissions/audits, database container recreation with the same new volume,
pg_dump checksums, row-for-row restore into the independent heshan_restore DB,
and real restored application health/schema validation.

Each command/assertion records PASS/FAIL, exit code, reason and timestamps in
result.json and execution.log. Expected negative tests can correctly be PASS
with a nonzero command exit code. All failure paths retain diagnostics and
attempt to stop only this project's containers. No down, prune, volume removal
or deletion of backups/results is performed. Stopped test containers, networks,
volumes, credentials and backups remain private pending owner approval.

The preparation directory retains preflight.log, rehearsal.log and a copy named
final-result.json. The integration directory retains result.json, execution.log,
container logs/state, resources.json, original single resource snapshot,
isolated.dump and its checksum. Every final path printed is absolute under
/var/tmp, never guessed from /tmp. Resource snapshots include Docker CPU/memory,
host MemAvailable/Swap, CPU counters/load and disk at startup, permissions,
persistence and restore. These are phase snapshots, not a peak-memory or load test.

Use interactive sudo to read the exact final-result.json path printed by the
command. Do not send test.env, full Docker inspect output, database backups or
credentials to chat. Share the redacted JSON/checks and printed final status.
Success requires ALL of: status PASS, containers_stopped true and exit code 0.
Otherwise formal deployment remains blocked until the failing check is resolved.

## Go-Live Boundary

This rehearsal does not modify SSH, sudoers, UFW, DNS, the legacy website or any
existing volume/database. It does not start a production database or switch
traffic. Successful VPS results would permit planning the separately approved
formal deployment, not immediate cutover. HTTPS/Pages/API staging, offsite backup
restore, monitoring, real owner-confirmed founder ID and final owner approval
remain gates listed in RELEASE_CANDIDATE.md.
