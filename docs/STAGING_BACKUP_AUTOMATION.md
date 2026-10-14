# Staging daily backup and offsite retention design

> PAUSED under the owner's MVP decision. Preserve this historical design and
> tests, but do not implement or enable the timer, rclone or B2 integration.
> Current manual-backup responsibilities and gaps: [V1 handover](V1_HANDOVER.md).

Status: LOCAL DESIGN AND MOCK TESTS ONLY. No VPS connection/configuration change,
provider registration, upload, alert delivery, scheduler installation, lifecycle
change or backup deletion was performed in this work. No production authorization.

## Existing components and evidence

- `staging-preupdate-backup.sh`: proven protected custom-format logical dump,
  SHA256 sidecar, archive listing, lock and backup report. Keep this script for
  approved idle preupdate/restart windows; it rejects concurrent before/after
  data changes and is not an appropriate unattended busy-site daily supervisor.
- `staging.py backup`: existing Staging collection with required ingress overlay;
  exports only, does not upload/prune. Its dump command/permission patterns can
  be reused without running a deploy command.
- `backup-postgresql.sh`: existing production export/offsite transfer. Its old
  age-only `find -delete` was removed locally because a successful upload exit
  does not prove each old remote copy is intact. Do not use production Compose
  to operate Staging or enable this old script as the new scheduler directly.
- Latest supplied VPS report: `/var/backups/heshan-staging` is root-only; the
  latest confirmed dump is `preupdate-20261014T000628Z-FDtl13l3.dump` with SHA256
  `80faf058d68d108e948a0bc3bd68d784ed623ec81bcc77aa23bd4bb6dec97cb4`.
  Earlier isolated restore passed; latest controlled restart persistence passed.
  No new live directory inspection was performed for this local-only task.

## Recommended workflow

Use a future approved systemd oneshot service and timer, once daily at 03:30 UTC
(23:30 previous day New York EDT; 22:30 EST). Use `Persistent=true` for one missed
run catch-up, `RandomizedDelaySec=300`, `AccuracySec=60`, no automatic restart
loop. A nonblocking owner-only `flock` shared with manual exports prevents
overlap. A busy lock is a reported SKIPPED event, never a success heartbeat.

1. Require only Staging project/service/database, expected persistent volume,
   healthy services, MemAvailable >=768 MiB, free disk >=4 GiB, no OOM and
   database logical size <=64 MiB for this small-site initial scope.
2. Export a custom-format single-worker dump (`pg_dump -Fc -Z 3`, app role,
   no owner/ACL) into a new random `.partial` file. Never put PGPASSWORD in
   argv or logs: use the existing container-local environment pattern.
3. Monitor resources/health, dump output bytes and elapsed time continuously;
   stop the backup workflow on limits, never stop/restart Staging services.
   Require a completed nonempty archive, local SHA256, and `pg_restore --list`
   without a target database. Atomically publish an exclusive filename only
   after validation; retain failed partials for owner inspection.
4. Use a separate daily namespace `/var/backups/heshan-staging/daily` (0700)
   with `daily-UTC_TIMESTAMP-16_RANDOM_HEX.dump` files (0600), matching SHA256
   sidecars, manifests and receipts. Never import/delete historical preupdate
   backups, restore reports, frozen copies or other directories.
5. Encrypt before leaving VPS using an independently configured rclone `crypt`
   remote over a private B2 bucket/prefix, with TLS. Upload one dump, checksum
   and a small manifest containing format version, SHA256, byte length,
   timestamp, project/database and Flyway version; no credentials or row bodies.
6. Download the full decrypted dump stream and verify SHA256 AND byte length.
   Separately download/decrypt and verify the checksum sidecar. Never treat
   ETag, size-only comparison or upload exit status as full verification.
7. Atomically record a private per-file receipt only after both checks pass.
   Send the success heartbeat only after local and offsite verification.
   Preserve local data on export/upload/download/verification/alert failures.
8. Produce a retention preview. Deletion is disabled in the present code. Any
   future pruning requires new explicit owner approval and in-lock revalidation
   immediately before acting. Never use `rclone sync`, global prune or `down -v`.

`pg_dump` makes a consistent backup during concurrent use; a before/after
record-count comparison is not a valid consistency requirement on a busy site.
For a same-backup fingerprint reference during a scheduled busy export, use a
reviewed exported PostgreSQL snapshot in both the dump and reference queries,
or compare two isolated restores of that backup against its signed/private
manifest. Do not compare a moving live database to an old dump and call it FAIL.
[PostgreSQL 16 documentation](https://www.postgresql.org/docs/16/app-pgdump.html).

## Retention safety

Local target 7 days, offsite target 30 days. Both are elapsed UTC days, not mtime
guessing. These are minimum safety policies, not unconditional deletion rules.

The implemented read-only `backup-retention-plan.py` only recognizes new daily
names. It hashes local content, verifies the checksum, permissions and no
symlink/hardlink alias, and reports candidates without deleting anything.
Old files require a matching approved remote identity, exact object name,
SHA256/size and sidecar proof, complete decrypted readback in the last 24 hours,
and a remote copy not expiring within 24 hours. Always keep the newest complete
local backup, even if older than 7 days. Missing/stale/failed receipts keep the
local file. An offsite outage can therefore exceed 7 local days: alert rather
than delete the only unconfirmed copy to free space.

Configure 30-day object lifecycle only on the dedicated Staging storage prefix
after approval. With crypt filename encryption, restrict lifecycle by the actual
encrypted storage prefix or a dedicated bucket; do not assume plaintext paths
remain visible. Check version/noncurrent-version and unfinished multipart rules
separately. This plan does not issue remote deletion commands. A 30-day offsite
policy can expire all remote copies after a prolonged outage; the retained newest
local copy and external missing-heartbeat alarm are essential safeguards.

Receipts are not cryptographic proof against a compromised root account. For
that threat, use provider object lock/immutable retention, owner-controlled
separate credentials, MFA and an offline recovery key. Prices/features need
confirmation before buying or enabling provider policies.

## Resource budget

Existing VPS: 1967 MiB RAM, 1 CPU, 1 GiB Swap; last restart test had minimum
1181 MiB available RAM and 2 MiB Swap used. No VPS upgrade is needed for the
current ~20 KiB dump size.

- Host supervisor/upload service: proposed `MemoryMax=256M`, `MemorySwapMax=0`,
  `CPUQuota=20%`, `TasksMax=40`, `Nice=10`, `IOSchedulingClass=idle`, maximum
  20-minute runtime, no parallel tasks. Validate systemd 255 directives on
  Ubuntu before installation, and do not change existing service limits.
- Export inside existing DB inherits its current 384 MiB / 0.35 CPU limit. The
  systemd host limit does NOT constrain a process launched via `docker exec`
  or PostgreSQL server queries. Monitor DB consumption independently. Serial
  low-compression export, DB lock timeout 5 seconds and statement timeout 10
  minutes bound disruption; a separate capped client container is a future
  option only if measurement shows it is necessary and the owner approves.
- Upload one stream only (`transfers=1`, `checkers=1`, small buffers and no
  multi-thread download). B2 multipart buffers can dominate memory; validate
  backend chunk limits with the selected pinned rclone version rather than
  relying on defaults. Keep an explicit 128 MiB uploader cap if using a
  dedicated container; do not assume host cgroups constrain it.
- Initial maximum dump size 128 MiB, daily namespace soft budget 2 GiB. Crossing
  a budget aborts/alerts without pruning. Monitor at <=2-second intervals during
  export/upload, available RAM >=768 MiB, disk >=4 GiB, no additional Swap.
- Streaming SHA256/download validation avoids loading a whole archive into RAM.
  No dump size growth beyond these limits is silently accepted.

## Cost comparison (official prices checked 2026-10-13)

Assume one backup per day, 30 retained dumps, small manifests/sidecars and modest
verification traffic. Estimates exclude tax, optional immutable retention,
shared-account usage, future growth and VPS transfer overages.

| Option | Pricing/limits | Current estimate |
| --- | --- | --- |
| Backblaze B2 (recommended) | First 10 GB free; then $6.95/TB-month, egress free up to 3x average stored data, excess $0.01/GB; API classes/rates vary | About $0/month at current size; independent provider from VPS/Cloudflare |
| Cloudflare R2 Standard | First 10 GB-month plus 1M Class A and 10M Class B requests free; then $0.015/GB-month; direct egress free | About $0/month at current size; requires separate approval to create/configure R2, no DNS change |
| DigitalOcean Spaces | $5/month minimum includes 250 GiB storage and 1 TiB outbound; overages extra | At least $5/month, convenient but same provider as VPS |
| Owner Mac/SFTP | No new storage subscription if hardware exists | Not reliable as sole unattended target: sleep/offline, connectivity and scheduling dependence |

At 100 MB/dump, 30 copies total about 3 GB: B2/R2 storage generally remains in
the quoted free allowance. At 1 GB/dump (~30 GB retained), storage-only estimates
are about $0.14/month for B2 above its allowance, $0.30/month for R2 above its
allowance, $5/month for Spaces before overages. This is a cost illustration,
not permission to lift the current 128 MiB dump cap.

[B2 prices](https://www.backblaze.com/cloud-storage/pricing),
[R2 prices](https://developers.cloudflare.com/r2/pricing/),
[Spaces prices](https://docs.digitalocean.com/products/spaces/details/pricing/).

## Failure and missing-run alerts

Use both systemd `OnFailure=` for immediate failures and an independently hosted
dead-man monitor for a missing verified daily heartbeat (VPS outage cannot send
its own failure alert). Proposed deadline: 26 hours since verified success,
plus a 1-hour grace. Lock conflict, offsite failure, checksum mismatch, low
resources and alert delivery failure never send success. Do not log webhook
URLs/tokens; keep them in a root-0600 curl config or credential file. Send only
site/environment, sanitized stage name, UTC timestamp and exit code, not dump
contents, usernames, database passwords, JWT or private reference data.

Healthchecks.io has a free hobby tier suitable for this small job count; owner
approval is still needed for account setup and external notifications. Verify
email delivery and missed-run alarms with a deliberate test. SMS/paid notification
integrations can add charges. [Official pricing](https://healthchecks.io/pricing/).

## Credentials and recovery

Private root-0700 directory `/etc/heshan-staging/backup/`; provider credentials,
crypt config and alert config root-0600. Do not put secrets in systemd unit text,
command arguments or repository examples. Existing .gitignore excludes env,
rclone.conf, key and dump files. Keep encryption recovery material securely
off VPS as well: B2/R2 cannot decrypt a crypt backup if its keys are lost.
Rclone obscure strings alone are not secure key storage.

Proposed nonsecret configuration names: `BACKUP_PROJECT=heshan-staging`,
`BACKUP_DATABASE=heshan_staging`, `BACKUP_DAILY_DIR=/var/backups/heshan-staging/daily`,
`BACKUP_REMOTE_ID=CHOOSE_PROVIDER_ACCOUNT_BUCKET_PREFIX`,
`BACKUP_CRYPT_REMOTE=CHOOSE_PRIVATE_CRYPT_REMOTE`,
`RCLONE_CONFIG=/etc/heshan-staging/backup/staging.backup-crypt.conf`,
`BACKUP_ALERT_CONFIG=/etc/heshan-staging/backup/staging.backup-alert.conf`,
`LOCAL_RETENTION_DAYS=7`, `OFFSITE_RETENTION_DAYS=30`. These are design placeholders,
not an active env file. Both credential-file suffixes are excluded from Git.

Database dumps include user password hashes and private community data even
though they do not include JWT, SSH or provider keys. Keep backups private and
encrypted offsite. Exported PostgreSQL role/password/ACL configuration is not
covered by the current no-owner/no-acl dump; reconstruct least-privilege roles
from reviewed deploy scripts and protect secrets separately.

## Periodic restore verification

Weekly: retrieve one offsite dump and sidecar on a trusted machine, decrypt and
check SHA256/size. Monthly: request approval for a restore to a wholly isolated
temporary container/database/volume; never schedule a source DB restore or restart.
Use existing hardened restore components, <=384 MiB RAM, 0.25 CPU, no additional
Swap/public ports, >=768 MiB available host RAM and >=4 GiB free disk. Verify
schema (including seven narrowly normalized enum CHECKs), table data, sequence
state, roles/founder protection and Flyway. Stop only the temporary target;
preserve its data and report until owner cleanup approval. A hash check alone
is not a restore rehearsal. Test again after migrations or database upgrades.

## Enable, pause and rollback gates

This is a design and tested retention planner, NOT an installed full daily
export/upload/alert supervisor. The existing collection/transfer patterns still
need integration into a reviewed daily runner after provider selection. Do not
install a timer pointing directly at the production backup script or idle-only
preupdate script and label that end-to-end verified automation.

Future enable sequence, each requiring owner approval:
1. Approve provider, monthly budget, private region/bucket/prefix and alert channel.
2. Approve required pinned tools/images; prepare private credentials/crypt config
   and store offline recovery material. Confirm no production prefix access.
3. Build/integrate the daily supervisor, lock, byte/time/resource gates, streaming
   upload verification and sanitized notifications; rerun local tests.
4. Run one manual end-to-end job, then download/decrypt from another machine;
   verify that failure preserves files and does not send success.
5. Approve the Staging-only 30-day provider lifecycle; test its exact scope.
6. Install reviewed systemd service/timer DISABLED, inspect with `systemd-analyze
   verify` and test failure/missing-run alarms. Only then approve activation with
   `systemctl enable --now heshan-staging-backup.timer`.
7. Keep local cleanup disabled initially. Review the 7-day planner output; any
   automatic cleanup executor needs separate approval and local/remote rechecks.

Pause: `systemctl disable --now heshan-staging-backup.timer` prevents future
triggers but does not stop a running oneshot. If one is active, preferably let
it finish; cancellation must target only this backup job/uploader and preserve
partials, never Docker services. Long pauses must also address remote lifecycle
expiry: stopping the timer does not stop provider deletion rules.

Rollback: keep timer disabled, restore the preceding approved backup-runner
version/config with protected ownership, validate it and run a manual smoke
job before re-enabling. Do not reinstate the old blind deletion command. Preserve
all backups/receipts; do not revoke the only crypt key or restore into Staging.
If an offsite credential is compromised, rotate provider access separately
while keeping the encryption recovery key available. No data rollback is part
of enabling or pausing backup automation.

## Remaining real-world validation

Local retention/readback logic and old-script no-prune behavior are mock-tested.
Real offsite transfer, encryption recovery, lifecycle scoping, cgroup enforcement,
systemd scheduling and alert delivery are NOT TESTED. Previously supplied restore
and persistence PASS evidence applies to those completed tests only. No external
service or scheduler is enabled by this document.
