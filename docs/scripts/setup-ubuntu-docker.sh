#!/usr/bin/env bash
set -Eeuo pipefail
set +x
umask 022
rollback_pending=false
daemon_existed=false
rollback_on_exit() {
    local status=$?
    trap - EXIT
    if (( status != 0 )) && [[ $rollback_pending == true ]]; then
        if [[ -L /etc/docker/daemon.json || ! -f /etc/docker/daemon.json ]] || ! cmp -s "$work/daemon.json" /etc/docker/daemon.json; then
            printf 'WARNING: daemon.json changed externally; automatic rollback refused. Backup: %s\n' "$work" >&2
        elif [[ $daemon_existed == true ]]; then
            if cp -a "$work/daemon.json.before" /etc/docker/daemon.json; then
                printf 'Restored original daemon.json.\n' >&2
                systemctl restart docker || printf 'WARNING: Docker restart after rollback failed.\n' >&2
            else
                printf 'WARNING: restoring daemon.json failed; backup: %s\n' "$work" >&2
            fi
        else
            if rm -- /etc/docker/daemon.json; then
                printf 'Removed only the daemon.json created by this run.\n' >&2
                systemctl restart docker || printf 'WARNING: Docker restart after rollback failed.\n' >&2
            else
                printf 'WARNING: removing the newly created daemon.json failed.\n' >&2
            fi
        fi
    fi
    exit "$status"
}
trap rollback_on_exit EXIT
trap 'printf "ERROR: stopped at line %s; inspect the failure before rerunning.\n" "$LINENO" >&2' ERR
trap 'exit 130' INT
trap 'exit 143' TERM

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
note() { printf '\n== %s ==\n' "$*"; }
installed() { [[ $(dpkg-query -W -f='${Status}' "$1" 2>/dev/null || true) == 'install ok installed' ]]; }
docker_local() { docker --host unix:///var/run/docker.sock "$@"; }
swap_capacity_bytes() {
    # Explicit columns/units avoid human-readable rounding and table alignment.
    swapon --show=SIZE --bytes --noheadings --raw | awk '
        NF != 1 || $1 !~ /^[0-9]+$/ {invalid=1; exit 2}
        {total += $1}
        END {if (!invalid) printf "%.0f", total}
    '
}
verify_swap_capacity() {
    local usable
    usable=$(swap_capacity_bytes)
    [[ $usable -ge $swap_min_usable_bytes ]] || die "Swap verification failed: usable=$usable bytes, required=$swap_min_usable_bytes bytes."
}
create_swap_file() {
    python3 - "$1" "$2" <<'PY'
import os
import sys

path, size = sys.argv[1], int(sys.argv[2])
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
try:
    fd = os.open(path, flags, 0o600)
except FileExistsError:
    raise SystemExit('Swap path already exists; no file was overwritten or truncated.')
try:
    os.fchmod(fd, 0o600)
    block = bytes(1024 * 1024)
    remaining = size
    while remaining:
        pending = memoryview(block)[:min(remaining, len(block))]
        while pending:
            written = os.write(fd, pending)
            if written <= 0:
                raise OSError('Swap write made no progress')
            remaining -= written
            pending = pending[written:]
    os.fsync(fd)
    if os.fstat(fd).st_size != size:
        raise OSError('Unexpected Swap file size')
except OSError:
    raise SystemExit('Swap creation failed; partial file retained for inspection. Do not delete or truncate it blindly.')
finally:
    os.close(fd)
PY
}
validate_swap_file() {
    [[ -f $swap && ! -L $swap ]] || die 'Swap path is not a regular file.'
    [[ $(stat -c '%s:%u:%a' "$swap") == "$swap_bytes:0:600" ]] || die 'Possible incomplete Swap file: unexpected size or permissions. Preserved unchanged; inspect before retrying.'
    [[ $(blkid -p -s TYPE -o value "$swap") == swap ]] || die 'Possible incomplete Swap file: no Swap signature. Preserved unchanged; inspect before retrying.'
}

[[ $# == 0 ]] || die 'No arguments are accepted.'
[[ $EUID == 0 ]] || die 'Run with sudo from a non-root SSH account.'
[[ -n ${SUDO_USER:-} && $SUDO_USER != root ]] || die 'Run through sudo, not a root login.'
# shellcheck disable=SC1091
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || die 'Only Ubuntu 24.04 is supported.'
command -v python3 >/dev/null || die 'Python 3 is required for safe JSON configuration merging.'
command -v flock >/dev/null || die 'flock is required.'

note 'Read-only security and resource checks'
systemctl is-active --quiet ssh || die 'SSH service is not active.'
ufw status verbose
ufw status | grep -qx 'Status: active' || die 'UFW is not active; no automatic firewall changes will be made.'
connection=${SSH_CONNECTION:-}
[[ -n $connection ]] || die 'SSH_CONNECTION is missing; preserve it explicitly through sudo.'
[[ $connection != *$'\n'* && $connection != *$'\r'* ]] || die 'Malformed multi-line SSH_CONNECTION.'
read -r client client_port server server_port extra <<< "$connection"
[[ -n $client && -n $client_port && -n $server && -n $server_port && -z $extra ]] || die 'Malformed SSH_CONNECTION.'
python3 - "$client" "$client_port" "$server" "$server_port" <<'PY'
import ipaddress
import sys

try:
    for address, port in zip(sys.argv[1::2], sys.argv[2::2]):
        ipaddress.ip_address(address)
        if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError('Invalid port')
except ValueError:
    raise SystemExit('Invalid SSH_CONNECTION address or port; no installation performed.')
PY
context="addr=$client,host=$client,laddr=$server,lport=$server_port"
sshd_effective=$(/usr/sbin/sshd -T -C "user=$SUDO_USER,$context")
root_effective=$(/usr/sbin/sshd -T -C "user=root,$context")
grep -qx 'permitrootlogin no' <<< "$root_effective" || die 'Root SSH login is not fully disabled.'
grep -qx 'passwordauthentication no' <<< "$sshd_effective" || die 'SSH password authentication is enabled.'
grep -qx 'kbdinteractiveauthentication no' <<< "$sshd_effective" || die 'SSH interactive authentication is enabled.'
grep -qx 'pubkeyauthentication yes' <<< "$sshd_effective" || die 'SSH public-key authentication is disabled.'
printf '%s\n' "$sshd_effective" | grep -E '^(permitrootlogin|passwordauthentication|pubkeyauthentication|kbdinteractiveauthentication) '
free -h
df -h /
[[ $(df --output=avail -B1 / | tail -n1) -ge 4294967296 ]] || die 'At least 4 GiB free disk space is required.'
exec 9>/run/lock/heshan-docker-setup.lock
flock -n 9 || die 'Another setup process is running.'

for package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
    if installed "$package"; then die "Conflicting package $package exists; nothing will be uninstalled automatically."; fi
done
if systemctl is-active --quiet docker; then
    [[ -z $(docker_local ps -aq) ]] || die 'Existing Docker containers found; refusing a potentially disruptive restart.'
elif [[ -d /var/lib/docker/containers ]] && [[ -n $(find /var/lib/docker/containers -mindepth 1 -maxdepth 1 -print -quit) ]]; then
    die 'Existing offline Docker container data found; refusing to start or modify Docker.'
fi
if command -v docker >/dev/null && ! installed docker-ce; then
    die 'An unmanaged Docker installation exists; inspect it manually first.'
fi

swap=/swapfile-heshan
swap_bytes=1073741824
# The first page holds the Swap header and is not usable Swap space.
swap_page_bytes=$(getconf PAGESIZE)
[[ $swap_page_bytes =~ ^[0-9]+$ ]] && (( swap_page_bytes > 0 && swap_page_bytes < swap_bytes )) || die 'Invalid kernel page size.'
swap_min_usable_bytes=$((swap_bytes - swap_page_bytes))
swap_was_present=false
note 'Inspect existing Swap and Docker configuration before installation'
if [[ -e /etc/docker/daemon.json || -L /etc/docker/daemon.json ]]; then
    [[ -f /etc/docker/daemon.json && ! -L /etc/docker/daemon.json ]] || die 'daemon.json is not a regular non-symlink file.'
    python3 -m json.tool /etc/docker/daemon.json >/dev/null
    printf 'Existing daemon.json found; custom settings will be retained and conflicts rejected.\n'
else
    printf 'daemon.json is absent (possibly removed by the previous rollback); no old backup will be blindly restored.\n'
fi
if [[ -e $swap || -L $swap ]]; then
    printf 'Existing Swap path detected: %s\n' "$swap"
    stat -c 'type=%F size=%s owner=%u permissions=%a' -- "$swap"
fi
active_swap=$(swap_capacity_bytes)
if (( active_swap > 0 && active_swap < swap_min_usable_bytes )); then
    die 'Existing usable Swap is below the 1 GiB target minus one header page; preserve it and review before adding more.'
fi
if (( active_swap == 0 )); then
    if awk '$0 !~ /^[[:space:]]*#/ && $3 == "swap" && $1 != "/swapfile-heshan" {found=1} END {exit !found}' /etc/fstab; then
        die 'Another inactive Swap entry exists in fstab; inspect it first.'
    fi
    if [[ -e $swap || -L $swap ]]; then
        validate_swap_file
        swap_was_present=true
    fi
fi

note 'Prepare official Docker repository'
export DEBIAN_FRONTEND=noninteractive
# Avoid automatic service restarts by needrestart during package installation.
export NEEDRESTART_MODE=l
apt-get update
apt-get install -y --no-remove -o Dpkg::Options::=--force-confold ca-certificates curl
install -d -m 0755 /etc/apt/keyrings
work=$(mktemp -d /var/tmp/heshan-docker-setup.XXXXXXXX)
chmod 0700 "$work"
printf 'Configuration backups and staging: %s\n' "$work"
arch=$(dpkg --print-architecture)
cat > "$work/docker.sources" <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $arch
Signed-By: /etc/apt/keyrings/docker.asc
EOF
if [[ -e /etc/apt/sources.list.d/docker.sources ]]; then
    cmp -s "$work/docker.sources" /etc/apt/sources.list.d/docker.sources || die 'Existing docker.sources differs; it will not be overwritten.'
fi
source_paths=(/etc/apt/sources.list.d)
[[ ! -f /etc/apt/sources.list ]] || source_paths+=(/etc/apt/sources.list)
if grep -RIl 'download.docker.com/linux/ubuntu' "${source_paths[@]}" | grep -v '^/etc/apt/sources.list.d/docker.sources$' >/dev/null; then
    die 'Another Docker repository entry exists; resolve it before rerunning.'
fi
if [[ ! -e /etc/apt/keyrings/docker.asc ]]; then
    curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
        https://download.docker.com/linux/ubuntu/gpg -o "$work/docker.asc"
    grep -q 'BEGIN PGP PUBLIC KEY BLOCK' "$work/docker.asc" || die 'Invalid Docker signing key response.'
    install -m 0644 "$work/docker.asc" /etc/apt/keyrings/docker.asc
fi
if [[ ! -e /etc/apt/sources.list.d/docker.sources ]]; then
    install -m 0644 "$work/docker.sources" /etc/apt/sources.list.d/docker.sources
fi
apt-get update

note 'Install missing Docker components without upgrading existing ones'
missing=()
for package in docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; do
    if installed "$package"; then
        printf 'Already installed; retaining: %s\n' "$package"
    else
        missing+=("$package")
    fi
done
if (( ${#missing[@]} > 0 )); then
    apt-get install -y --no-remove -o Dpkg::Options::=--force-confold "${missing[@]}"
fi

note 'Merge and validate Docker log rotation'
install -d -m 0755 /etc/docker
[[ ! -L /etc/docker/daemon.json ]] || die 'daemon.json is a symlink; refusing to replace it.'
python3 - "$work/daemon.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path('/etc/docker/daemon.json')
config = json.loads(path.read_text()) if path.exists() else {}
if not isinstance(config, dict):
    raise SystemExit('Docker configuration must be a JSON object.')
if 'hosts' in config:
    raise SystemExit('Custom Docker listener configuration exists; inspect it first.')
if config.get('log-driver', 'json-file') != 'json-file':
    raise SystemExit('Existing logging driver differs; configuration left unchanged.')
options = config.setdefault('log-opts', {})
if not isinstance(options, dict):
    raise SystemExit('Docker log-opts must be a JSON object.')
limits = {'max-size': '10m', 'max-file': '3'}
if any(key in options and options[key] != value for key, value in limits.items()):
    raise SystemExit('Existing custom log rotation limits differ; configuration left unchanged.')
config['log-driver'] = 'json-file'
options.update(limits)
pathlib.Path(sys.argv[1]).write_text(json.dumps(config, indent=2) + '\n')
PY
dockerd --validate --config-file "$work/daemon.json"
changed=false
if ! cmp -s "$work/daemon.json" /etc/docker/daemon.json; then
    if [[ -e /etc/docker/daemon.json ]]; then
        cp -a /etc/docker/daemon.json "$work/daemon.json.before"
        daemon_existed=true
    fi
    staged_daemon=$(mktemp /etc/docker/.heshan-daemon.XXXXXXXX)
    install -m 0644 "$work/daemon.json" "$staged_daemon"
    mv -f -- "$staged_daemon" /etc/docker/daemon.json
    rollback_pending=true
    changed=true
fi
systemctl enable docker.service containerd.service
if [[ $changed == true ]]; then
    systemctl restart docker
else
    systemctl start docker
fi

note 'Configure persistent 1 GiB Swap without replacing existing Swap'
if (( active_swap == 0 )); then
    if [[ $swap_was_present == false ]]; then
        create_swap_file "$swap" "$swap_bytes"
        mkswap "$swap"
    fi
    validate_swap_file
    swapon "$swap"
    if ! awk '$0 !~ /^[[:space:]]*#/ && $1 == "/swapfile-heshan" && $3 == "swap" {found=1} END {exit !found}' /etc/fstab; then
        cp -a /etc/fstab "$work/fstab.before"
        printf '\n/swapfile-heshan none swap sw 0 0\n' >> /etc/fstab
    fi
else
    printf 'Existing active Swap retained; no extra Swap created.\n'
fi

note 'Installation verification (no application or database deployment)'
systemctl is-active docker containerd ssh
docker_local version
docker_local compose version
[[ $(docker_local info --format '{{.LoggingDriver}}') == json-file ]] || die 'Unexpected active Docker logging driver.'
docker_local run --rm --network none --memory 64m --cpus 0.5 --pids-limit 64 hello-world
swapon --show --bytes
verify_swap_capacity
free -h
df -h /
ufw status verbose
ss -lntup
rollback_pending=false
printf '\nCompleted. No SSH/UFW/DNS configuration changes, application deployment, or database deployment performed.\n'
printf 'Docker itself creates networking rules. Backups/staging retained at: %s\n' "$work"
