# Ubuntu 24.04 Docker Setup (Stage Two)

Status: prepared for review only. Do not execute until the owner confirms.

Script: `docs/scripts/setup-ubuntu-docker.sh`.

## Scope

- Requires Ubuntu 24.04, a non-root SSH session, interactive sudo, Python 3,
  active UFW and key-only SSH with root SSH login disabled.
- Installs missing Docker Engine, CLI, containerd, Buildx and Compose Plugin
  through Docker's official Ubuntu repository. Existing Docker packages are
  not intentionally upgraded; apt can still change required dependencies.
- Preserves other Docker JSON settings; configures `json-file` logging with
  `max-size=10m` and `max-file=3` (approximately 30 MB per container).
- Creates `/swapfile-heshan` (1 GiB, root-owned, mode 0600) only when no Swap
  is active. Existing active Swap meeting the usable-capacity threshold is
  retained, not resized. The threshold is 1 GiB minus one kernel header page.
- Adds a single fstab entry for the new Swap. Does not change swappiness.
- Runs the official hello-world verification container with no network,
  no published ports and small resource limits. Removes only this newly
  created test container on exit; retains its image for repeat verification.
- Does not deploy Spring Boot/PostgreSQL, publish ports, change SSH/sudoers,
  UFW rules, DNS, existing websites, Docker group memberships or databases.
- Docker itself creates network/firewall rules. This is not equivalent to
  editing UFW rules; published container ports can bypass UFW in future.
- No passwords are accepted as arguments, embedded, logged or piped to sudo.
  Do not execute with `bash -x` or record a password-entry session.

## Review And Execute After Confirmation

Review the complete script locally before authorizing it. From the Mac:

```bash
scp -i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=yes \
  /Users/qizhitang/Documents/heshan.net/docs/scripts/setup-ubuntu-docker.sh \
  heshan@165.232.156.104:~/heshan-docker-setup-review.sh

ssh -t -i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=yes \
  heshan@165.232.156.104 \
  'sudo --preserve-env=SSH_CONNECTION /bin/bash "$HOME/heshan-docker-setup-review.sh"'
```

Before uploading, confirm the remote review filename is unused, or reuse
only the copy previously uploaded for this task. Never overwrite an unrelated
file. The sudo prompt accepts the server account password directly in the
local terminal, with no character echo. Do not send the password to chat.
Both commands are instructions only; no upload or execution has occurred yet.
Only the non-secret SSH connection metadata is preserved for the security
context check. If sudo policy rejects that option, stop for review; do not
change sudoers or bypass the check.

## Repeat Execution And Failure Handling

- Re-running does not duplicate fstab entries, resize existing Swap, remove
  packages, remove existing containers or intentionally upgrade Docker.
- Existing containers, conflicting packages, differing repository settings,
  an incompatible logging driver, unexpected Swap files and inactive Swap
  configured elsewhere cause a stop rather than automatic destructive repair.
- Keep application deployments stopped while running; do not create containers
  concurrently. This script is intended for initial server setup, not for
  maintenance on a server already hosting containers.
- Config backups/staging are retained in the printed root-only directory
  `/var/tmp/heshan-docker-setup.*`. They contain configuration, not credentials
  intentionally collected by the script; existing Docker settings may be
  sensitive, so do not publish them.
- Failure stops subsequent steps but does not undo installed packages or
  already completed changes. Inspect the failing step before rerunning.
- Any failure after replacing daemon JSON restores the previous file, or
  removes only the file newly created by this run if no original existed.
  This also handles INT/TERM, but cannot handle SIGKILL or power loss. If the
  configuration has subsequently changed externally, rollback stops rather
  than overwriting that change. Recovery errors are reported, not hidden.
  Do not automatically uninstall Docker or delete `/var/lib/docker`.
- Existing conflicting custom log limits are not overwritten. Other custom
  settings are retained. JSON replacement uses a same-directory atomic rename.
- SSH_CONNECTION must contain exactly two valid IP addresses and two valid
  ports. Missing/malformed metadata causes an exit before installation. All
  SSH security checks precede package installation and other setup changes.
- If Swap creation is interrupted before initialization, the partial file is
  left untouched and the next run stops for inspection. No existing file is
  truncated to repair it automatically.
- Swap allocation uses Python's exclusive creation (`O_CREAT | O_EXCL |
  O_NOFOLLOW`) and explicit zero writes, not the unsupported `dd oflag=excl`.
  Short writes are handled; size is checked and data synchronized before
  initialization. Existing files and symlinks are never truncated.
- Removing newly configured Swap requires checking available RAM first,
  disabling only `/swapfile-heshan` and restoring its fstab entry from backup;
  this is a separate authorized operation. No automatic rollback deletes it.

## Verification And Limitations

The script prints effective SSH settings, UFW rules, Docker client/server and
Compose versions, logging driver, hello-world result, Swap, memory, disk and
listening ports. Log limits apply to newly created containers. This preparation
has only local syntax/static checks; production installation and reboot
persistence are not verified until it is authorized and run.

Local isolated safety tests (no installer or system service execution):

```bash
bash -n docs/scripts/setup-ubuntu-docker.sh
python3 docs/scripts/test_setup_ubuntu_docker.py
```

These cover JSON merging and custom limits, IPv4/IPv6 metadata, missing or
malformed SSH metadata, rollback with/without an original file, external
configuration changes and security-check ordering. Run ShellCheck as well
when it is already available; it is not an installation prerequisite.

## Retry After The Reported Swap Failure

The reported `Removed only the daemon.json created by this run` means that
run had no original daemon JSON and removed its own new configuration. It
does not prove Docker was uninstalled or that the current file is absent.
No remote state was inspected during this local repair.

Upload the fixed script under a new review filename (or replace only the
known prior copy), then use the same SSH + sudo invocation documented above.
Do not run the old remote script again. Enter the sudo password only in the
terminal; do not use `sudo -S`, a password environment variable or a log file.

Before package installation, the fixed script inspects `/swapfile-heshan`
and validates its type, size, ownership, mode and Swap signature if inactive.
An incomplete or ambiguous file causes a safe stop. Do not blindly delete,
truncate, chmod or initialize it; inspect the reported state first. A valid
inactive file can be reused, and sufficient active Swap is retained.

It validates any current daemon JSON without printing its contents, merges
only non-conflicting logging defaults, and never blindly restores a backup
from an earlier run. Already-installed Docker packages and Compose are
retained; only missing components are requested. Existing containers cause
a stop rather than a restart. Backups from earlier runs remain untouched.

Regression tests also cover exclusive creation, existing files/symlinks,
partial write and sync failures, retry refusal, incomplete-file preflight
and Docker config rollback when Swap creation fails. Tests use temporary
small files; they do not allocate real Swap or invoke mkswap/swapon.

## Swap Verification Header Correction

A 1 GiB Swap file on a system with 4096-byte pages has 1073741824 bytes of
file storage but 1073737728 bytes of usable Swap. The header occupies one
page. `/proc/swaps` reports 1048572 KiB for the latter, not 1048576 KiB.
Human-readable `swapon --show` can round this to `1024M`.

The previous verification compared usable bytes against file bytes and
incorrectly failed. This was a threshold error, not a parsing error in the
observed `/proc/swaps` row. Both initial active-Swap checks and final checks
now use explicit `swapon --show=SIZE --bytes --noheadings --raw`
and compare the usable total against `1 GiB - getconf PAGESIZE`. Malformed
output and genuinely insufficient capacity still fail. Multiple small areas
are checked conservatively against that same usable-capacity threshold.
Ubuntu 24.04's util-linux 2.39.3 does not provide a separate `--output SIZE`
column selector for swapon. Use `--show=SIZE`; the alternative was observed
to produce multiple columns and is rejected by the regression tests.

Do not recreate an already-active valid Swap file to fix this report. A
verification failure may already have rolled back daemon JSON while leaving
Docker and persistent Swap installed. Inspect logging separately; do not
rerun the whole installer when only logging remains unconfigured.

References:

- https://docs.docker.com/engine/install/ubuntu/
- https://docs.docker.com/engine/logging/drivers/json-file/
- https://docs.docker.com/engine/network/packet-filtering-firewalls/
- https://docs.python.org/3/library/os.html#os.open
- https://man7.org/linux/man-pages/man8/mkswap.8.html
- https://man7.org/linux/man-pages/man8/swapon.8.html
