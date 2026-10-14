# Staging restart persistence: preparation only

No restart, stop, recreation, update, backup creation or recovery is authorized
by this document. Obtain a new explicit owner approval before those actions.

## Read-only findings (2026-10-13)

Direct SSH checks, without sudo, returned:

- Ubuntu 24.04.5 LTS, one logical CPU, 1967 MiB physical RAM.
- MemAvailable 1198 MiB; used RAM 769 MiB.
- Swap 1023 MiB, used 2 MiB; existing swapfile remains untouched.
- Root filesystem approximately 41 GiB available.
- Load average 0.02 / 0.07 / 0.08.
- HTTPS listener 127.0.0.1:18443; no host 8080 or 5432 listener observed.
- `sudo -n true` failed: interactive sudo password required.

The owner's subsequent privileged read-only report returned PASS:

- All three containers healthy, OOM=false, automatic restart count 0.
- MemAvailable 1197 MiB, Swap used 2 MiB, free disk 43195895808 bytes.
- Actual DB mount is local volume `heshan-staging_staging_data`, read/write at
  `/var/lib/postgresql/data`; source is
  `/var/lib/docker/volumes/heshan-staging_staging_data/_data`.
- Latest backup is `preupdate-20261013T021045Z-iDCXZKC2.dump`, 20564 bytes;
  checksum `c0faf8c68855cd5fb1961ee1f45a4770ac8e00a956d815bd284d4ee108586c68`
  and archive listing both passed. The earlier isolated restore and reverification
  validate recovery of this specific backup.
- Backend/Web active files include release `2e176e0de59784297e3253c97806db09989dc7fe`
  and `/etc/heshan-staging/web-ingress.override.yml`. Overlay SHA256 is
  `a6f5ee400296d5629e049e001253bd2f51af94536482e4f6bca1f93a75cf051e`.
- DB still references the original `eca42d278f39c64415f9946fec9f51aa6c113459`
  release. This reflects preservation of the original DB container, not a failed
  application update. Do not run an all-service Compose `up` during this test.
- Baseline: users 5, posts 9, comments 9, role audit 0, founder records 0,
  ghost ID 1 remains USER; Flyway V1 successful.

These are preparation checks only. Restart persistence is still NOT TESTED,
and resource/identity/backup gates must be repeated immediately before an
approved execution.

The local Compose uses an independent named `staging_data` volume, no DB/backend
host ports, `unless-stopped` for all three services and these startup conditions:

```text
db healthy -> backend -> backend healthy -> web
```

Limits are PostgreSQL 384 MiB / 0.35 CPU, Backend 768 MiB / 0.60 CPU and Web
64 MiB / 0.10 CPU (1216 MiB combined RAM limits). Limits are not actual usage;
host memory, page cache and other services still need headroom.

The local controller refuses to operate if an installed ingress overlay is
omitted. The installed version and active config files must still be verified.
`depends_on` is startup ordering, not automatic recovery orchestration when a
running PostgreSQL service later restarts. Backend connection recovery must be
tested explicitly. `unless-stopped` does not fix an unhealthy running process.

## Owner's read-only terminal check

On the Mac, run:

```bash
python3 /Users/qizhitang/Documents/heshan.net/docs/scripts/persistence-readonly-check.py
```

The local launcher sends Python source as an SSH command, not as an uploaded
server file. Interactive sudo reads its password in the terminal. The checker
only inspects Docker state, reads resources/configuration/archive metadata and
runs SELECTs in a READ ONLY transaction. It neither reads `staging.env` nor
prints container environment values, healthcheck bodies or archive contents.

It verifies the latest `.dump` by file modification time, root-only permissions,
exact checksum sidecar/path binding and `pg_restore --list` without a target DB.
It evaluates recorded Web Compose files with the existing overlay and
`--no-interpolate --env-file /dev/null`, printing only deployment-related fields.
If a required path, health, owner role, checksum or resource check fails, stop.

Archive listing/checksum verifies basic integrity; the retained isolated restore
provides actual recovery evidence for its specific backup. A newer untested
backup cannot automatically inherit that PASS result. Capture freshness and
create a new read-only logical backup before the future restart, only after
owner approval.

## Proposed staged execution (NOT EXECUTED)

Arrange a maintenance window, stop browser test writes voluntarily and keep
the SSH tunnel open. Do not change production traffic or DNS.

1. Preflight: all three containers healthy, no OOM/unexpected restart; verify
   exact container IDs/images, source volume name/path, private ingress and
   the active base Compose plus overlay. Require MemAvailable >=768 MiB and
   disk >=4 GiB. Capture baseline CPU/Swap and memory limits.
2. With approval, create a new logical backup of Staging, verify SHA256 and
   archive listing. Preserve it and all older backups. Capture six table counts
   and full-row fingerprints, roles/identities, ghost USER, empty founder table,
   Flyway, sequences and schema definitions before any restart.
3. Restart Backend ONLY, once. DB and Web must retain their container IDs and
   mounts. Wait up to 240 seconds for Backend health, then verified HTTPS/API
   requests and read-only database baseline equality. Expected interruption:
   API calls may briefly fail while Backend restarts; Web remains running.
4. Only after stage 3 passes, restart PostgreSQL ONLY, once, with a graceful
   stop timeout (proposed 60 seconds). Do not recreate it. Wait up to 180
   seconds for DB health and successful read-only SQL. Then allow Backend up
   to 240 seconds to recover connectivity, verify API/HTTPS and baseline equality.
   During DB restart, Backend health can temporarily degrade; this is expected
   only within the approved recovery window.
5. Final: all services healthy; original IDs, images and mounts unchanged;
   ghost USER/founder empty; counts/full-row fingerprints, roles, Flyway,
   sequences and schema equivalent; private port binding preserved. Recheck OOM,
   automatic restart counts, resources and sanitized error indicators. Preserve
   a protected PASS/FAIL report. Web need not be restarted for this test.

Continuously monitor during the execution. Abort advancement on available RAM
below 768 MiB, disk below 4 GiB, OOM, unexpected automatic restart, unrelated
service failure, integrity/owner mismatch or timeout. Warn/pause on sustained
CPU pressure or Swap growth (proposed >128 MiB above the captured baseline).
Do not disable/increase Swap or change limits in this validation.

"Abort" means stop the test flow and preserve evidence, not stop other services.
Do not repeatedly restart a failing service. Do not automatically perform a
second Backend restart if PostgreSQL reconnection fails: explain the condition
and obtain owner approval for the recovery action.

## Failure containment and rollback

A restart does not change code, Compose, container image or volume identity,
so there is no new application release to roll back. There is also no automatic
data rollback: restoring an older dump could lose newer records.

- Backend failure: leave DB/Web and their data intact, gather restricted logs,
  resource state and the unchanged baseline. Diagnose before any further action.
- PostgreSQL failure: do not remove/recreate the container or data directory.
  Inspect exit/health/resource state. Starting the same stopped container is a
  separately approved recovery action, not an automatic retry loop.
- Data/role mismatch: stop the verification workflow immediately; preserve the
  volume and reports. Do not restore over Staging. Any investigation restore must
  use a separately approved isolated target.
- If a prior image rollback/recreation becomes necessary, request new approval
  and explicitly use BOTH the recorded release Compose and
  `/etc/heshan-staging/web-ingress.override.yml`, the same project name and env
  file. Do not use an old controller missing the overlay.
- Never run first-install, founder initialization, `down -v`, volume deletion,
  global prune, production actions or DNS changes.

Restarting an existing container retains its installed networks and port
bindings; it does not re-read Compose or remove the overlay. A future recreation
does re-evaluate configuration, so both Compose files must remain explicit.

## Approval needed next

After the privileged read-only report passes, ask for approval for a fresh
logical backup, Backend restart once, then PostgreSQL restart once, baseline
SQL comparison, HTTPS/API checks and resource monitoring. No container
recreation, deployment, second recovery retry or source database restore is
included. This plan does not claim restart persistence has already passed.

## Approved execution package

The owner subsequently approved this staged execution. The prepared runner is
`docs/scripts/verify-staging-restart-persistence.py`; regression cases verify
that backup failure performs no restart and Backend health/data/resource
failure prevents a PostgreSQL restart. PostgreSQL timeout never triggers an
automatic second restart. Only the two confirmed full container IDs may be
restarted, once each, with the same mounts/images/ingress and existing data.

The Mac launcher is `/tmp/heshan-persistence-on-mac.sh`. It uses interactive sudo,
copies the approved four runtime files into a new root-only directory and
verifies SHA256 before execution. The VPS incoming package is
`/var/tmp/heshan-persistence-bundle-Zbjhv26O`. Uploaded files are preparation
only; the application and database have not been restarted by the agent.

Stop browser test writes and run once, keeping the SSH session open:

```bash
bash /tmp/heshan-persistence-on-mac.sh
```

The script prints its absolute report directory, starting with
`/var/tmp/heshan-persistence-report-`. It preserves `result.json`, command exit
metadata, resource samples, protected data snapshots and a fresh database backup.
Raw SQL output and command error bodies are not printed. Existing Docker logs
remain in place. Only the summary report is suitable for sharing; do not paste
baseline files or env files. If FAIL or SSH disconnect occurs, inspect the
report/current state; do not automatically rerun the launcher.

Actual VPS persistence verification remains NOT TESTED until the owner executes
the package and the final report confirms PASS.
