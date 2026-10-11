#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ ${EUID} -eq 0 ]] || { printf '%s\n' 'Interactive sudo is required.' >&2; exit 1; }
[[ $# -eq 1 ]] || { printf '%s\n' 'Supply the uploaded minimal build-context directory.' >&2; exit 1; }
for tool in docker python3 sha256sum mktemp; do
  command -v "$tool" >/dev/null || { printf 'Missing prerequisite: %s\n' "$tool" >&2; exit 1; }
done
[[ -S /var/run/docker.sock ]] || { printf '%s\n' 'Local Docker socket unavailable.' >&2; exit 1; }
docker_local() { docker --host unix:///var/run/docker.sock "$@"; }
docker_local info --format 'Docker Server: {{.ServerVersion}}'
docker_local compose version
[[ -z $(docker_local ps -q) ]] || { printf '%s\n' 'Running containers found; stopping preparation.' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || { printf '%s\n' 'This preparation requires an AMD64 VPS.' >&2; exit 1; }
available=$(awk '/MemAvailable:/ {print int($2/1024)}' /proc/meminfo)
printf 'Available RAM: %s MiB\n' "$available"
[[ $available -ge 1300 ]] || { printf '%s\n' 'Insufficient available RAM.' >&2; exit 1; }
free -h
df -h /var/tmp
[[ $(df -Pk /var/tmp | awk 'END {print $4}') -ge 4194304 ]] || { printf '%s\n' 'At least 4 GiB free disk is required.' >&2; exit 1; }
if docker_local image inspect heshan-backend:pg-test >/dev/null 2>&1; then
  printf '%s\n' 'Backend test tag already exists; refusing to overwrite it. Review image identity first.' >&2
  exit 1
fi

source_dir=$(cd -- "$1" && pwd)
for file in Dockerfile .dockerignore target/backend-0.0.1-SNAPSHOT.jar SHA256SUMS; do
  [[ -f "$source_dir/$file" && ! -L "$source_dir/$file" ]] || { printf '%s\n' 'Incomplete or symlinked build context.' >&2; exit 1; }
done
workspace=$(mktemp -d /var/tmp/heshan-image-build-XXXXXXXX)
mkdir -p "$workspace/target" "$workspace/docs/scripts" "$workspace/deploy"
cp -- "$source_dir/Dockerfile" "$source_dir/.dockerignore" "$source_dir/SHA256SUMS" "$workspace/"
cp -- "$source_dir/target/backend-0.0.1-SNAPSHOT.jar" "$workspace/target/"
for file in prepare-vps-postgresql-images.sh run-vps-postgresql-test.sh test-vps-postgresql.py pg-test-compose.yml; do
  cp -- "$source_dir/docs/scripts/$file" "$workspace/docs/scripts/"
done
cp -- "$source_dir/deploy/postgres-init.sh" "$workspace/deploy/"
cd "$workspace"
sha256sum --check SHA256SUMS
printf 'Retained root-private build context: %s\n' "$workspace"
if ! docker_local image inspect postgres:16-bookworm >/dev/null 2>&1; then
  docker_local pull --platform linux/amd64 postgres:16-bookworm
fi
[[ $(docker_local image inspect --format '{{.Os}}/{{.Architecture}}' postgres:16-bookworm) == linux/amd64 ]] || {
  printf '%s\n' 'Unexpected PostgreSQL image architecture; no resources removed.' >&2; exit 1;
}
docker_local buildx version
# Runtime image only: reviewed Dockerfile copies the prebuilt JAR; no Maven runs here.
docker_local build --platform linux/amd64 -t heshan-backend:pg-test .
[[ $(docker_local image inspect --format '{{.Os}}/{{.Architecture}}' heshan-backend:pg-test) == linux/amd64 ]]
docker_local image inspect --format '{{.RepoTags}} {{.Os}}/{{.Architecture}} {{.Id}}' postgres:16-bookworm heshan-backend:pg-test
printf '%s\n' 'Images ready. No database or website was started. Run the isolated test wrapper next.'
