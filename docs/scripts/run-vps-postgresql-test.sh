#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ ${EUID} -ne 0 ]]; then
  printf '%s\n' 'Run through interactive sudo. Do not enable root SSH or change Docker group membership.' >&2
  exit 1
fi
if [[ $# -ne 1 || -z $1 || $1 == *[[:space:]]* || $1 == *=* ]]; then
  printf '%s\n' 'Usage: sudo bash run-vps-postgresql-test.sh PRELOADED_BACKEND_IMAGE' >&2
  exit 1
fi
for command in python3 docker flock mktemp tee; do
  command -v "$command" >/dev/null || { printf 'Required command unavailable: %s\n' "$command" >&2; exit 1; }
done
[[ -S /var/run/docker.sock ]] || { printf '%s\n' 'Local Docker socket unavailable.' >&2; exit 1; }
exec 9>/run/lock/heshan-postgresql-integration.lock
flock -n 9 || { printf '%s\n' 'Another test wrapper is running.' >&2; exit 1; }

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for file in test-vps-postgresql.py pg-test-compose.yml ../../deploy/postgres-init.sh; do
  [[ -f "$source_dir/$file" && ! -L "$source_dir/$file" ]] || { printf '%s\n' 'Incomplete or symlinked test bundle.' >&2; exit 1; }
done
# Copy reviewed scripts to a root-owned workspace before privileged execution.
workspace=$(mktemp -d /var/tmp/heshan-it-bundle-XXXXXXXX)
mkdir -p "$workspace/docs/scripts" "$workspace/deploy"
cp -- "$source_dir/test-vps-postgresql.py" "$source_dir/pg-test-compose.yml" "$workspace/docs/scripts/"
cp -- "$source_dir/../../deploy/postgres-init.sh" "$workspace/deploy/"
chmod -R go-rwx "$workspace"
# PostgreSQL runs initialization as its non-root container user.
chmod 0644 "$workspace/deploy/postgres-init.sh"
printf 'Protected execution workspace: %s\n' "$workspace"
printf '%s\n' 'Only isolated test resources will be created. No installation, image pull or cleanup is performed.'
set +e
env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
  DOCKER_HOST=unix:///var/run/docker.sock PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
  python3 "$workspace/docs/scripts/test-vps-postgresql.py" --execute-isolated-tests --image "$1" --report-dir "$workspace" \
  2>&1 | tee "$workspace/launcher.log"
statuses=("${PIPESTATUS[@]}")
status=${statuses[0]}
if [[ ${statuses[1]} -ne 0 ]]; then status=1; fi
set -e
if ! python3 - "$workspace/result.json" <<'PY'
import json
from pathlib import Path
import sys
try:
    report = json.loads(Path(sys.argv[1]).read_text())
    success = report.get("status") == "PASS" and report.get("containers_stopped") is True
except (OSError, ValueError):
    success = False
sys.exit(0 if success else 1)
PY
then status=1; fi
printf 'Test exit code: %s\nExecution log: %s/execution.log\nResult JSON: %s/result.json\nLauncher log: %s/launcher.log\n' "$status" "$workspace" "$workspace" "$workspace"
printf '%s\n' 'Keep this workspace and the printed test data directory. Nothing is automatically deleted.'
exit "$status"
