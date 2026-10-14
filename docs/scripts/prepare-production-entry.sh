#!/usr/bin/env bash
# Owner-run entry preparation only. No database, TLS issuance or DNS operations.
set -Eeuo pipefail
set +x
umask 077
[[ $EUID == 0 && $# == 1 && $1 == --execute-entry-preparation ]] || exit 1
[[ $(uname -s) == Linux ]] || exit 1
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || exit 1
unset DOCKER_CONTEXT
export DOCKER_HOST=unix:///var/run/docker.sock
DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
(cd "$DIR"; sha256sum -c SHA256SUMS)
for path in /etc/heshan /srv/heshan /etc/systemd/system/nginx.service; do
  [[ ! -e $path && ! -L $path ]] || { printf 'STOP: existing path %s\n' "$path"; exit 1; }
done
for package in nginx nginx-common; do
  [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true) != 'install ok installed' ]] || {
    printf 'STOP: Nginx already installed; review instead of reinstalling.\n'; exit 1;
  }
done
awk '/MemAvailable:/ {if ($2 < 786432) exit 1}' /proc/meminfo
df -Pk / | awk 'NR == 2 {if ($4 < 4194304) exit 1}'
[[ -z $(ss -H -ltn '( sport = :80 or sport = :443 or sport = :8080 )') ]] || exit 1

snapshot() {
  docker inspect heshan-staging-db-1 heshan-staging-backend-1 heshan-staging-web-1 \
    --format '{{.Id}} {{.State.Status}} {{.State.Health.Status}} {{.State.OOMKilled}} {{.RestartCount}}'
}
baseline=$(snapshot)
[[ $(printf '%s\n' "$baseline" | awk '$2=="running" && $3=="healthy" && $4=="false" && $5==0 {n++} END {print n+0}') == 3 ]] || exit 1
python3 - <<'PY'
import ipaddress, json, subprocess
target = ipaddress.ip_network('172.30.10.0/24')
ids = subprocess.check_output(['docker', 'network', 'ls', '-q'], text=True).split()
networks = json.loads(subprocess.check_output(['docker', 'network', 'inspect', *ids])) if ids else []
for network in networks:
    for item in (network.get('IPAM') or {}).get('Config') or []:
        if item.get('Subnet'):
            subnet = ipaddress.ip_network(item['Subnet'])
            if subnet.version == target.version and subnet.overlaps(target):
                raise SystemExit('STOP: production subnet overlaps existing Docker network')
print('PASS: production subnet does not overlap existing Docker networks')
PY
printf 'PASS: healthy Staging, resources, ports and network preflight\n'
started=0
finish() {
  code=$?
  trap - EXIT
  if [[ $code != 0 && $started == 1 ]]; then
    systemctl stop nginx || printf 'WARNING: could not stop newly installed Nginx\n' >&2
    systemctl disable nginx || printf 'WARNING: could not disable newly installed Nginx\n' >&2
  fi
  printf 'Entry preparation exit code: %s; no database or DNS commands executed.\n' "$code"
  exit "$code"
}
trap finish EXIT
apt-get update
export NEEDRESTART_MODE=l
started=1
apt-get install -y --no-install-recommends nginx
systemctl stop nginx
systemctl disable nginx
if systemctl is-active --quiet nginx; then printf 'STOP: Nginx still active\n'; exit 1; fi
if systemctl is-enabled --quiet nginx; then printf 'STOP: Nginx still enabled\n'; exit 1; fi
install -d -m 0700 -o root -g root /etc/heshan /etc/heshan/tls
install -d -m 0755 -o root -g root /srv/heshan /srv/heshan/releases
install -m 0600 -o root -g root "$DIR/nginx-site-https.conf.example" /etc/heshan/nginx-site-https.conf.example
install -m 0600 -o root -g root "$DIR/cloudflare-realip.conf.example" /etc/heshan/cloudflare-realip.conf.example
[[ $(snapshot) == "$baseline" ]] || { printf 'STOP: Staging state changed; investigate\n'; exit 1; }
nginx -v
free -m
df -h /
printf 'PASS: Nginx installed/stopped/disabled; draft templates only; Staging unchanged.\n'
printf 'Do not rerun: existing directories are intentionally protected from overwrite.\n'
