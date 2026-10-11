# Isolated PostgreSQL Rehearsal

## Comma-Separated Tmpfs Fix

The confirmed Docker error `invalid mount path: 'mode=1777'` occurred BEFORE
Spring Boot started. The YAML flow list `[/tmp:size=64m,mode=1777]` parses as two
strings: `/tmp:size=64m` and `mode=1777`. The latter is not an absolute target.
Both test and production Compose now use a block list with a quoted scalar:

```yaml
tmpfs:
  - "/tmp:size=64m,mode=1777"
```

This retains the 64 MiB tmpfs, sticky permissions, read-only root filesystem,
capability drop, no-new-privileges, memory limits and private database network.
Other bind/volume targets were reviewed; no SSH/UFW/DNS/data change is needed.
The wrapper itself needs no mount change. A new startup preflight examines
`docker compose config --format json` WITHOUT logging its secret-bearing stdout
and rejects relative mount targets or missing backend tmpfs options before
creating containers. `config --quiet` alone did not detect the old invalid path.

Tests use the Docker CLI's real YAML/Compose parser (no daemon) for test,
production and GeoIP override configurations, preserve security assertions and
reproduce/reject the original malformed YAML. This verifies configuration,
NOT real container startup; rerun the full VPS test to confirm Spring/Flyway/
Hibernate/founder/restore. No backend image rebuild is needed for this fix.

Upload the corrected script-only bundle on the Mac:

```bash
cd /Users/qizhitang/Documents/heshan.net
bash docs/scripts/package-vps-postgresql-test.sh /private/tmp/heshan-pg-mount-fix-v1.tar.gz
scp -i ~/.ssh/id_ed25519 /private/tmp/heshan-pg-mount-fix-v1.tar.gz heshan@165.232.156.104:~/
ssh -t -i ~/.ssh/id_ed25519 heshan@165.232.156.104
```

In the ordinary heshan session, stop if mkdir fails; never overwrite an old run:

```bash
mkdir -m 700 ~/heshan-pg-mount-fix-v1
tar --keep-old-files -xzf ~/heshan-pg-mount-fix-v1.tar.gz -C ~/heshan-pg-mount-fix-v1
cd ~/heshan-pg-mount-fix-v1
sudo env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
  bash docs/scripts/run-vps-postgresql-test.sh heshan-backend:pg-test
```

Keep old test resources/reports; the retry creates a new project/volume. This
test package contains corrected test Compose and its existing scripts only;
`deploy/compose.yml` is fixed in the local repository for future deployment,
NOT uploaded into production. Read result.json and container logs using the
exact printed `/var/tmp` paths. Require PASS and containers_stopped=true.

## Diagnostic Runner Update

The old runner wrote its first check only after DB startup, backend health,
Flyway history and role queries all succeeded. It discarded subprocess output
and printed a generic exception, so FAIL with checks=[] does NOT prove no
commands ran. A PostgreSQL-ready message does not prove Flyway or Hibernate
succeeded. The actual backend/SQL failure needs container logs, not guessing.

The updated wrapper uses ONE root-private absolute `/var/tmp/heshan-it-bundle-*`
directory for `execution.log`, `launcher.log`, `result.json`, test credentials,
backups, resource snapshots and diagnostics. Every command/assertion is recorded
as RUNNING then PASS/FAIL with exit code, reason and UTC timestamps. Timeout
code is 124, operator interruption 130. Expected rejected founder commands may
show PASS with nonzero command code and an explicit explanation; their rejection
is separately asserted. The JSON is saved atomically after each transition.

Logs retain command stdout/stderr, including Spring/Flyway/psql errors, with
known test credentials/JWTs redacted. Auth-response/SQL-row stdout and binary
backup bytes are deliberately not placed in execution.log. Container logs are
captured before and after stop, plus each container's state/health/OOM/exit-code.
No full environment inspection is logged. These are sensitive root-private
diagnostic artifacts even after redaction; review before sharing.

One-off founder/restore containers are now retained (no `--rm`) so their logs
survive. Stop is restricted to the exact new project, including any still-running
one-off container. Volumes, reports, backups, networks and stopped containers
are not deleted. If Docker itself is unavailable, log capture reports that
failure; no script can manufacture inaccessible container logs. SIGKILL/power
loss cannot guarantee final stop; inspect the recorded project before retrying.

The wrapper additionally checks result.json, requiring status PASS and
containers_stopped=true, not only Python exit code. Backend image/business code
has not changed for this diagnostic update; rebuild is unnecessary if the
previous image is current. No PostgreSQL compatibility success is claimed until
the revised real test passes.

### Upload Updated Scripts And Retry

On the Mac, choose a NEW archive path:

```bash
cd /Users/qizhitang/Documents/heshan.net
bash docs/scripts/package-vps-postgresql-test.sh /private/tmp/heshan-pg-diagnostics-v1.tar.gz
scp -i ~/.ssh/id_ed25519 /private/tmp/heshan-pg-diagnostics-v1.tar.gz heshan@165.232.156.104:~/
ssh -t -i ~/.ssh/id_ed25519 heshan@165.232.156.104
```

In that ordinary heshan SSH session, stop if mkdir fails (do not overwrite):

```bash
mkdir -m 700 ~/heshan-pg-diagnostics-v1
tar --keep-old-files -xzf ~/heshan-pg-diagnostics-v1.tar.gz -C ~/heshan-pg-diagnostics-v1
cd ~/heshan-pg-diagnostics-v1
sudo env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
  bash docs/scripts/run-vps-postgresql-test.sh heshan-backend:pg-test
```

Password goes ONLY into sudo's terminal prompt. Existing image tags must already
be loaded; this script does not build or pull images. Existing stopped previous
test projects are preserved; running containers cause safe refusal. Use only the
absolute final printed paths to read result.json, execution.log and
before-stop-container-logs.log. Do not combine /tmp data from old runners with
/var/tmp data from this runner. Do not share test.env or auth bodies.

## Scope And Confirmed Decisions

The owner does not require any previous H2 data. Production PostgreSQL will
start empty; no H2 export/import is planned. This does not authorize deleting
any existing server resource. `ghost` is a planned username only, never code.
All registrations remain USER. Founder promotion requires verified ID and exact
username confirmation through the offline server command, not a public API.

This rehearsal has not been executed on a VPS. No SSH, DNS or production change
is part of this preparation. No Mac PostgreSQL installation is needed.

## Approval Required Before Execution

Confirm an execution window, the exact prebuilt backend image/digest, transfer
method, image download/storage allowance and permission to create a unique
temporary Docker network/volume and protected test directory. Confirm that no
other running container or memory-heavy service will be impacted. The script
refuses existing running containers and requires at least 1300 MiB available
RAM, but this is not a substitute for reviewing other non-container services.

Do not execute on the legacy server. Use the already prepared new VPS only.
Database/app containers publish NO ports; all traffic stays within one new
internal Docker network. Limits are 384 MiB PostgreSQL + 768 MiB backend,
0.35 + 0.60 CPU. Backend is stopped before offline initialization and restore
validation, so a second JVM does not compete for memory. Backups are tiny
synthetic fixtures, not a production dataset. Docker root access is powerful;
only trusted server operators may run this script or the real founder command.

## Prepare On Mac Or CI

Use Java 17 and build locally, never Maven on the VPS:

```bash
cd /Users/qizhitang/Documents/heshan.net/backend
JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home mvn package
```

The Mac currently has no Docker daemon. Build the amd64 image in a separately
approved CI/builder and securely transfer/load it on the VPS. Do not presume
the fixture image already exists. Package the repository deployment scripts
with the image artifact; the test uses `deploy/postgres-init.sh`. No credentials
are bundled. A reviewed backend image based on the existing Dockerfile must
contain Java 17, curl and `/app/app.jar`.

## Proposed VPS Steps (Not Executed)

1. Read-only review: available memory/disk, Docker version, running containers
   and other services. Verify SSH/UFW are unchanged. Verify image provenance.
2. Load the approved backend image (example tag `heshan-backend:pg-test`) and
   explicitly pull the approved `postgres:16-bookworm` image. Pulling consumes
   network/disk; the test itself never pulls images. Record resolved digests.
3. Place project files in a separate test directory with restricted access.
   With a local Docker socket and Python 3, run:

```bash
python3 docs/scripts/test-vps-postgresql.py \
  --execute-isolated-tests --image heshan-backend:pg-test
```

Use interactive `sudo` only if local Docker permissions require it; never put
the sudo password into commands or files, and do not modify sudoers. Do not
pass production secrets. Script generates random TEST-ONLY DB/JWT credentials
in a mode-600 file inside a mode-700 directory. It refuses remote Docker sockets.
The protected test directory and unique `heshan-it-*` project name are printed,
not credentials or tokens. Do not print Compose's expanded config or env file.

4. The script verifies empty schema, Flyway migration and Hibernate validate;
   application DB role is not a PostgreSQL superuser/create-role/create-DB role;
   malicious registration role is ignored; USER cannot access admin APIs.
5. An arbitrary synthetic owner name (not `ghost`) is created. Wrong ID
   confirmation must fail without a founder row. Offline initialization must
   succeed once, create audit and reject repetition. It never touches a real
   founder account. ADMIN cannot grant SUPER_ADMIN or modify the founder;
   founder cannot be demoted through the API; revoked ADMIN's old JWT is denied.
6. Fixture posts/comments are inserted. Recreating the DB container retains the
   unique volume; restarting backend repeats Flyway validation without replaying
   V1. Previously issued token still works and audits remain.
7. Dump test database to protected local file with SHA-256 checksum. Restore
   into a separate `heshan_restore` database in the SAME isolated test PostgreSQL
   container to avoid another 384 MiB container. Compare every row of all six
   tables including Flyway history. Start the real backend against restored
   schema to verify Flyway/Hibernate/health, then stop it.
8. On success/failure, stop ONLY this Compose project's containers. Preserve
   volume, credentials and backup for inspection. No automatic volume deletion,
   no `down -v`, no database wipe, no production promotion.

## Results, Failure And Cleanup

A PASS requires all assertions. A nonzero exit or timeout is failure; do not
proceed to production. Error messages intentionally omit subprocess output to
avoid accidental token/secret logging. A trusted operator can privately inspect
the exact project's container state, without sharing env/expanded config/logs
containing sensitive information. Capture the project name and artifact digest.

Cleanup is a separate owner-approved operation: identify resources by the exact
random project label, verify no production dependencies, then review removing
only that project's stopped containers/network/volume and protected test files.
Do not use global prune or delete other data. Until cleanup, test backups and
credential files remain on the VPS; do not run this repeatedly without checking
disk usage.

This tests local dump/restore, NOT external storage availability, provider
retention, encryption or disaster recovery outside the VPS. Rehearse the
offsite workflow from `PRODUCTION.md` after selecting/approving a provider.
Actual Pages hosting/HTTPS, concurrency races, real load and image vulnerability
review remain separate release gates. Application-managed audit is not
tamperproof against a trusted DBA who controls the database credentials.

## Local Regression Commands

### Interactive Sudo Bundle

No root SSH, Docker group membership, sudoers, firewall or DNS change is needed.
The bundle has a fixed whitelist of four scripts/config files, no credentials
or application/database files. Review them before running privileged code.
Package from the Mac (choose a fresh archive path):

```bash
cd /Users/qizhitang/Documents/heshan.net
bash docs/scripts/package-vps-postgresql-test.sh /private/tmp/heshan-pg-test.tar.gz
scp -i ~/.ssh/id_ed25519 /private/tmp/heshan-pg-test.tar.gz heshan@165.232.156.104:~/
ssh -t -i ~/.ssh/id_ed25519 heshan@165.232.156.104
```

Within that ordinary `heshan` SSH session, choose a NEW directory so nothing
existing is overwritten (if `mkdir` fails, stop and choose another path):

```bash
mkdir -m 700 ~/heshan-pg-test-01
tar -xzf ~/heshan-pg-test.tar.gz -C ~/heshan-pg-test-01
cd ~/heshan-pg-test-01
sudo env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
  bash docs/scripts/run-vps-postgresql-test.sh heshan-backend:pg-test
```

Enter sudo password ONLY at the terminal prompt. Do not use `sudo -S`, pipe a
password, enable shell tracing, or share the env file. This command does not
pull/load/build images or install tools. Both the reviewed backend image and
`postgres:16-bookworm` MUST already be loaded locally; otherwise it safely fails.
Image provisioning remains a separate approved prerequisite, not accomplished
by uploading the script bundle. Lock prevents concurrent wrapper execution.

The wrapper snapshots scripts into a new root-owned mode-700 `/var/tmp` workspace
and clears Docker context/host overrides. The Python runner creates a second
protected test data directory. Record BOTH printed paths and unique project name.
Results: `result.json`, `resources.txt`, `host-memory.txt`, `project.txt`, optional
`isolated.dump` and checksum in the test data directory; `execution.log` in the
execution workspace. No raw credentials/subprocess response bodies are logged.
Logs are milestone/error summaries, not raw application/container log exports.
After completion use actual printed paths/names in these inspection examples:

```bash
sudo cat /tmp/REPLACE_WITH_TEST_DATA_DIRECTORY/result.json
sudo cat /tmp/REPLACE_WITH_TEST_DATA_DIRECTORY/resources.txt
sudo cat /var/tmp/REPLACE_WITH_EXECUTION_WORKSPACE/execution.log
sudo docker ps -a --filter label=com.docker.compose.project=REPLACE_WITH_PROJECT
sudo docker volume ls --filter label=com.docker.compose.project=REPLACE_WITH_PROJECT
sudo docker network ls --filter label=com.docker.compose.project=REPLACE_WITH_PROJECT
```

Require exit code 0, report status PASS and `containers_stopped: true`. Any
failure means stop; do not deploy or attempt destructive fixes. Missing images,
active containers, low memory or unavailable Docker socket are refusal conditions.
Existing containers/networks/volumes are not removed or modified. Only newly
created test containers may be recreated for persistence testing or removed as
one-off `--rm` command containers; the test database volume is retained. All
main test containers are stopped at completion. Credentials and backups are
root-private and retained until separately approved cleanup.

```bash
python3 docs/scripts/test_vps_postgresql_test.py
python3 docs/scripts/test_backup_postgresql.py
```

Backend tests cover incorrect identity, arbitrary confirmed username, blank/null
confirmation, persistent H2 test storage, memory DB rejection, singleton audit,
registration injection, ADMIN denial and stale JWT revocation. PostgreSQL
Testcontainers tests remain skipped without a local daemon; this VPS rehearsal
is an additional real-PostgreSQL verification, not a claim it has already passed.
