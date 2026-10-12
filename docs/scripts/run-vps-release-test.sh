#!/usr/bin/env bash
set -euo pipefail
umask 077

[[ ${EUID} -eq 0 ]] || { printf '%s\n' 'Run using interactive sudo in your terminal.' >&2; exit 1; }
[[ $# -ge 2 && $# -le 3 && $2 =~ ^[0-9a-f]{40}$ ]] || { printf '%s\n' 'Usage: sudo bash run-vps-release-test.sh UPLOADED_BUNDLE_DIR EXPECTED_GIT_SHA [TEST_FOUNDER_USERNAME]' >&2; exit 1; }
founder_username=${3:-ghost}
[[ $founder_username =~ ^[A-Za-z0-9_-]{3,50}$ ]] || { printf '%s\n' 'Invalid test founder username.' >&2; exit 1; }
for tool in docker python3 sha256sum mktemp flock; do
  command -v "$tool" >/dev/null || { printf 'Missing prerequisite: %s\n' "$tool" >&2; exit 1; }
done
[[ -S /var/run/docker.sock && $(uname -m) == x86_64 ]] || { printf '%s\n' 'Local AMD64 Docker server required.' >&2; exit 1; }
exec 8>/run/lock/heshan-release-image.lock
flock -n 8 || { printf '%s\n' 'Another release image preparation is running.' >&2; exit 1; }
docker_local() { env -u DOCKER_CONTEXT docker --host unix:///var/run/docker.sock "$@"; }
source_dir=$(cd -- "$1" && pwd)
revision=$2
image="heshan-backend:$revision"
files=(backend-image.tar SOURCE_REVISION SHA256SUMS docs/scripts/run-vps-release-test.sh docs/scripts/run-vps-postgresql-test.sh
       docs/scripts/test-vps-postgresql.py docs/scripts/pg-test-compose.yml deploy/postgres-init.sh)
for file in "${files[@]}"; do
  [[ -f "$source_dir/$file" && ! -L "$source_dir/$file" ]] || { printf 'Missing or symlinked bundle file: %s\n' "$file" >&2; exit 1; }
done
workspace=$(mktemp -d /var/tmp/heshan-release-test-XXXXXXXX)
mkdir -p "$workspace/docs/scripts" "$workspace/deploy"
for file in "${files[@]}"; do cp -- "$source_dir/$file" "$workspace/$file"; done
cd "$workspace"
printf 'Retained image/preflight workspace: %s\n' "$workspace"
exec > >(tee "$workspace/preflight.log") 2>&1
[[ $(cat SOURCE_REVISION) == "$revision" ]] || { printf '%s\n' 'Source revision mismatch.'; exit 1; }
# Require exactly the approved files; never accept checksum paths outside this bundle.
python3 - <<'PY'
from pathlib import Path
import re
expected = {'backend-image.tar', 'SOURCE_REVISION', 'docs/scripts/run-vps-release-test.sh', 'docs/scripts/run-vps-postgresql-test.sh',
            'docs/scripts/test-vps-postgresql.py', 'docs/scripts/pg-test-compose.yml', 'deploy/postgres-init.sh'}
lines = Path('SHA256SUMS').read_text().splitlines()
entries = [re.fullmatch(r'([0-9a-f]{64})  (.+)', line) for line in lines]
if any(entry is None for entry in entries) or len(entries) != len(expected) or {entry[2] for entry in entries} != expected:
    raise SystemExit('Invalid checksum manifest; no Docker resources changed.')
PY
sha256sum --check SHA256SUMS
docker_local version
docker_local compose version
docker_local ps -a --format '{{.Names}} {{.Status}} {{.Ports}}'
docker_local network ls
docker_local volume ls
docker_local info --format 'Logging driver: {{.LoggingDriver}}'
if [[ -f /etc/docker/daemon.json ]]; then
  python3 - <<'PY'
import json
from pathlib import Path
config = json.loads(Path('/etc/docker/daemon.json').read_text())
print('Docker logging configuration:', json.dumps({key: config.get(key) for key in ('log-driver', 'log-opts')}))
PY
fi
[[ -z $(docker_local ps -q) ]] || { printf '%s\n' 'Running containers detected; aborting without stopping any service.'; exit 1; }
available=$(awk '/MemAvailable:/ {print int($2/1024)}' /proc/meminfo)
printf 'Available memory: %s MiB\n' "$available"
[[ $available -ge 1300 ]] || { printf '%s\n' 'Insufficient memory; no images loaded.'; exit 1; }
free -h
swapon --show --bytes
df -h "$workspace"
[[ $(df -Pk "$workspace" | awk 'END {print $4}') -ge 4194304 ]] || { printf '%s\n' 'At least 4 GiB free disk required.'; exit 1; }
# Inspect archive metadata before load; reject extra tags, wrong platform or source.
archive_ids=$(python3 - "$image" "$revision" <<'PY'
import hashlib
import json
import sys
import tarfile
with tarfile.open('backend-image.tar') as archive:
    manifest = json.load(archive.extractfile('manifest.json'))
    if len(manifest) != 1 or manifest[0].get('RepoTags') != [sys.argv[1]]:
        raise SystemExit('Archive must contain only the approved SHA-tagged backend image.')
    config_bytes = archive.extractfile(manifest[0]['Config']).read()
    config = json.loads(config_bytes)
    if (config.get('os'), config.get('architecture')) != ('linux', 'amd64'):
        raise SystemExit('Archive is not linux/amd64.')
    if config.get('config', {}).get('Labels', {}).get('org.opencontainers.image.revision') != sys.argv[2]:
        raise SystemExit('Archive source revision mismatch.')
    config_id = 'sha256:' + hashlib.sha256(config_bytes).hexdigest()
    identities = {config_id}
    # Docker's classic store reports config ID; Engine 29/containerd can report
    # an OCI manifest/index ID. Accept only verified descriptors of this config.
    def inspect_descriptor(descriptor):
        digest = descriptor['digest']
        if not digest.startswith('sha256:'):
            raise SystemExit('Unsupported archive digest.')
        value = archive.extractfile('blobs/sha256/' + digest.split(':', 1)[1]).read()
        if 'sha256:' + hashlib.sha256(value).hexdigest() != digest:
            raise SystemExit('Archive descriptor checksum mismatch.')
        model = json.loads(value)
        valid = model.get('config', {}).get('digest') == config_id
        if 'manifests' in model:
            valid = any([inspect_descriptor(child) for child in model['manifests']])
        if valid:
            identities.add(digest)
        return valid
    if 'index.json' in archive.getnames():
        index = json.load(archive.extractfile('index.json'))
        for descriptor in index['manifests']:
            name = descriptor.get('annotations', {}).get('io.containerd.image.name')
            if name not in (sys.argv[1], 'docker.io/library/' + sys.argv[1]):
                raise SystemExit('Unexpected OCI image reference in archive.')
            if not inspect_descriptor(descriptor):
                raise SystemExit('OCI descriptor does not reference approved image config.')
    print(' '.join(sorted(identities)))
PY
)
if docker_local image inspect "$image" >/dev/null 2>&1; then
  existing_id=$(docker_local image inspect --format '{{.Id}}' "$image")
  [[ " $archive_ids " == *" $existing_id "* ]] || {
    printf '%s\n' 'Existing SHA tag has another image; refusing to overwrite it.'; exit 1;
  }
else
  docker_local load --input backend-image.tar
fi
loaded_id=$(docker_local image inspect --format '{{.Id}}' "$image")
[[ " $archive_ids " == *" $loaded_id "* ]]
[[ $(docker_local image inspect --format '{{.Os}}/{{.Architecture}}' "$image") == linux/amd64 ]]
if ! docker_local image inspect postgres:16-bookworm >/dev/null 2>&1; then
  docker_local pull --platform linux/amd64 postgres:16-bookworm
fi
[[ $(docker_local image inspect --format '{{.Os}}/{{.Architecture}}' postgres:16-bookworm) == linux/amd64 ]]
docker_local image inspect --format '{{.RepoTags}} {{.Id}} {{.Os}}/{{.Architecture}}' "$image" postgres:16-bookworm
# Release preparation lock is separate from the integration wrapper's lock.
set +e
bash docs/scripts/run-vps-postgresql-test.sh "$image" "$founder_username" "$revision" 2>&1 | tee "$workspace/rehearsal.log"
statuses=("${PIPESTATUS[@]}")
status=${statuses[0]}
if [[ ${statuses[1]} -ne 0 ]]; then status=1; fi
set -e
if ! python3 - "$workspace" <<'PY'
import json
from pathlib import Path
import re
import shutil
import sys
workspace = Path(sys.argv[1])
matches = re.findall(r'^Result JSON: (/var/tmp/heshan-it-bundle-[A-Za-z0-9]+/result.json)$',
                     (workspace / 'rehearsal.log').read_text(), re.MULTILINE)
if len(matches) != 1:
    raise SystemExit('No unique final test report; inspect retained rehearsal.log.')
report = json.loads(Path(matches[0]).read_text())
shutil.copyfile(matches[0], workspace / 'final-result.json')
print('Final result copy:', workspace / 'final-result.json')
print('Final report status:', report.get('status'))
print('Containers stopped:', report.get('containers_stopped'))
print('Checks recorded:', len(report.get('checks', [])))
if report.get('status') != 'PASS' or report.get('containers_stopped') is not True:
    raise SystemExit('Release rehearsal did not pass; retain all artifacts.')
PY
then status=1; fi
printf 'Release rehearsal exit code: %s\nRetained preparation log: %s/preflight.log\n' "$status" "$workspace"
exit "$status"
