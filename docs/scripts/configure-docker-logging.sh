#!/usr/bin/env bash
set -Eeuo pipefail
set +x
umask 077

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
docker_local() { docker --host unix:///var/run/docker.sock "$@"; }
require_no_running_containers() {
    [[ -z $(docker_local ps -q) ]] || die 'Running or paused containers found; no Docker restart is permitted.'
}
restart_after_rollback() {
    local running
    if running=$(docker_local ps -q 2>/dev/null) && [[ -z $running ]]; then
        systemctl restart docker || printf 'WARNING: Docker recovery restart failed.\n' >&2
    else
        printf 'WARNING: cannot confirm no running containers; recovery restart skipped. Inspect Docker manually.\n' >&2
    fi
}

rollback_pending=false
original_exists=false
finish() {
    local status=$?
    trap - EXIT
    if (( status != 0 )) && [[ $rollback_pending == true ]]; then
        if [[ -L $config || ! -f $config ]] || ! cmp -s "$work/candidate.json" "$config"; then
            printf 'WARNING: configuration changed externally; rollback refused. Backup directory: %s\n' "$work" >&2
        elif [[ $original_exists == true ]]; then
            if cp -p "$work/daemon.json.before" "$config"; then
                printf 'Restored the original daemon.json.\n' >&2
                restart_after_rollback
            else
                printf 'WARNING: configuration restore failed. Backup directory: %s\n' "$work" >&2
            fi
        else
            if rm -- "$config"; then
                printf 'Removed only daemon.json created by this run.\n' >&2
                restart_after_rollback
            else
                printf 'WARNING: removing the newly created config failed.\n' >&2
            fi
        fi
    fi
    exit "$status"
}
trap finish EXIT
trap 'printf "ERROR: stopped at line %s.\n" "$LINENO" >&2' ERR
trap 'exit 130' INT
trap 'exit 143' TERM

[[ $# == 0 ]] || die 'No arguments are accepted.'
[[ $EUID == 0 ]] || die 'Run using sudo from a non-root account.'
[[ -n ${SUDO_USER:-} && $SUDO_USER != root ]] || die 'Use sudo, not a root SSH login.'
for command in docker dockerd python3 systemctl flock; do
    command -v "$command" >/dev/null || die "Required command missing: $command. Nothing will be installed."
done
exec 9>/run/lock/heshan-docker-setup.lock
flock -n 9 || die 'Another Docker configuration operation is running.'

printf 'Checking existing Docker service and local daemon.\n'
systemctl is-active --quiet docker || die 'Docker is not active; inspect its state before configuring logging.'
docker_local version
[[ $(docker_local info --format '{{.LoggingDriver}}') == json-file ]] || die 'The active logging driver is customized; refusing to override it.'
unit_command=$(systemctl show docker --property=ExecStart --value)
if [[ $unit_command == *--config-file* || $unit_command == *--log-driver* || $unit_command == *--log-opt* ]]; then
    die 'Custom Docker config/logging startup flags found; inspect them before using this script.'
fi

config=/etc/docker/daemon.json
[[ ! -L /etc/docker ]] || die '/etc/docker is a symlink; refusing to modify it.'
[[ ! -L $config ]] || die 'daemon.json is a symlink; refusing to modify it.'
work=$(mktemp -d /var/tmp/heshan-docker-logging.XXXXXXXX)
chmod 0700 "$work"
printf 'Root-only backup/staging directory: %s\n' "$work"
if [[ -e $config ]]; then
    [[ -f $config ]] || die 'daemon.json is not a regular file.'
    cp -p "$config" "$work/daemon.json.before"
    original_exists=true
fi

python3 - "$work" <<'PY'
import json
import pathlib
import sys

work = pathlib.Path(sys.argv[1])
backup = work / 'daemon.json.before'
original = json.loads(backup.read_text()) if backup.exists() else {}
if not isinstance(original, dict):
    raise SystemExit('daemon.json must be a JSON object; no configuration changed.')
config = dict(original)
if config.get('log-driver', 'json-file') != 'json-file':
    raise SystemExit('Existing custom log-driver conflicts; no configuration changed.')
options = config.get('log-opts', {})
if not isinstance(options, dict):
    raise SystemExit('log-opts must be a JSON object; no configuration changed.')
limits = {'max-size': '10m', 'max-file': '3'}
if any(key in options and options[key] != value for key, value in limits.items()):
    raise SystemExit('Existing custom log limits conflict; no configuration changed.')
config['log-driver'] = 'json-file'
config['log-opts'] = {**options, **limits}
(work / 'candidate.json').write_text(json.dumps(config, indent=2) + '\n')
(work / 'changed').write_text('yes' if original != config else 'no')
PY
dockerd --validate --config-file "$work/candidate.json"
if [[ $(< "$work/changed") == no ]]; then
    printf 'Logging configuration already matches; no changes or restart performed.\n'
    exit 0
fi

require_no_running_containers
install -d -m 0755 /etc/docker
staged=$(mktemp /etc/docker/.heshan-logging.XXXXXXXX)
if [[ $original_exists == true ]]; then
    cp -p "$work/daemon.json.before" "$staged"
    cat "$work/candidate.json" > "$staged"
else
    install -m 0644 "$work/candidate.json" "$staged"
fi
# Recheck both the configuration snapshot and running containers before commit.
if [[ $original_exists == true ]]; then
    [[ ! -L $config ]] && cmp -s "$work/daemon.json.before" "$config" || die 'daemon.json changed concurrently; refusing to overwrite it.'
else
    [[ ! -e $config && ! -L $config ]] || die 'daemon.json appeared concurrently; refusing to overwrite it.'
fi
require_no_running_containers
mv -f -- "$staged" "$config"
rollback_pending=true
require_no_running_containers
systemctl restart docker
systemctl is-active --quiet docker
[[ $(docker_local info --format '{{.LoggingDriver}}') == json-file ]] || die 'Active logging driver verification failed.'
cmp -s "$work/candidate.json" "$config" || die 'Configuration changed during verification.'
rollback_pending=false
printf 'Configured json-file logging: max-size=10m, max-file=3.\n'
printf 'Applies to newly created containers; existing containers were not modified.\n'
printf 'No package, Swap, SSH, UFW, DNS, sudoers, application or database changes performed.\n'
