# Docker Logging Only

Status: prepared locally; not uploaded or executed on the VPS.

Script: `docs/scripts/configure-docker-logging.sh`.

## Behavior

Requires an installed, active Docker daemon, dockerd, Python 3, systemd,
flock and sudo from a non-root account. It installs nothing. It uses the
local Unix socket explicitly, not DOCKER_HOST or a remote Docker context.

Target defaults for newly created containers:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Existing JSON settings and file permissions are retained. Conflicting log
drivers/limits, malformed JSON, symlinks, customized runtime log drivers and
custom config/logging startup flags cause a stop. No conflicting value is
overwritten. A matching configuration is not rewritten or restarted.

Before changing the config, the script backs it up in a root-only directory
printed as `/var/tmp/heshan-docker-logging.*`. Backups may contain sensitive
existing settings; do not upload them or publish their contents. It validates
the candidate using `dockerd --validate --config-file`, checks running/paused
containers before commit and restart, and atomically replaces daemon JSON.

Run only in a maintenance window with no concurrent container starts or
configuration edits. The script does not stop containers to make a restart
possible. The lock coordinates with the project's installer, not unrelated
administrators or tools. A stopped existing container is retained unchanged.

On failure after applying the candidate, it restores the original file or
removes only this run's new daemon JSON. Externally changed configurations
are not overwritten during rollback. Recovery restarts are attempted only
when the local daemon confirms no running containers; if it cannot be
contacted, or containers are running, the script reports that manual recovery
is needed. INT/TERM trigger rollback, but SIGKILL/power loss cannot be caught.
Package state, Swap, SSH, UFW rules, DNS, sudoers, applications and databases
are not changed. Docker restart itself can refresh its own networking rules.

It does not pull images, create test containers, recreate existing containers,
remove Docker data or modify existing container logs. Rotation is approximately
30 MB per container. Existing containers do not inherit new defaults; restarting
them is not enough. Any future recreation must be a separate authorized task.

## Mac Terminal Execution After Confirmation

Use a new review filename and only this script, not the full installer:

```bash
remote_script="heshan-docker-logging-$(date +%Y%m%d-%H%M%S).sh"
scp -i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=yes \
  /Users/qizhitang/Documents/heshan.net/docs/scripts/configure-docker-logging.sh \
  "heshan@165.232.156.104:$remote_script"

ssh -t -i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=yes \
  heshan@165.232.156.104 \
  "sudo /bin/bash \"\$HOME/$remote_script\""
```

Run both commands in the same Mac terminal. Enter the sudo password only
at its terminal prompt, without echo. No password is embedded, logged,
piped, or saved. SSH_CONNECTION preservation is not required by this
logging-only script. No sudoers change is needed.

## Local Checks

```bash
bash -n docs/scripts/configure-docker-logging.sh
python3 docs/scripts/test_configure_docker_logging.py
```

Tests use temporary paths and mocked Docker/systemd commands; they do not
contact the VPS or operate the local Docker daemon. They cover absent and
existing configs, backups, custom settings, conflicts, syntax validation
failure, running-container protection, rollback and repeat execution.
The real dockerd validator and daemon behavior remain to be checked when
execution is authorized. Run ShellCheck when available; do not install it
on the VPS solely for these tests.

Official references:

- https://docs.docker.com/engine/logging/drivers/json-file/
- https://docs.docker.com/reference/cli/dockerd/
