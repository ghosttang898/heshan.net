#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $# -ge 2 && $# -le 4 && $1 =~ ^[0-9a-f]{40}$ ]] || { printf '%s\n' 'Usage: bash package-vps-release-test.sh VERIFIED_GIT_SHA NEW_OUTPUT_DIR [VERIFIED_JAR] [SOURCE_CHECKOUT]'; exit 1; }
revision=$1
output=$2
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source_root=${4:-$root}
cd "$source_root"
for tool in git docker python3 shasum tar; do command -v "$tool" >/dev/null; done
[[ -z ${DOCKER_CONTEXT:-} ]] || { printf '%s\n' 'Unset DOCKER_CONTEXT; local Docker only.'; exit 1; }
endpoint=${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}
[[ $endpoint == unix://* ]] || { printf '%s\n' 'Local Unix Docker endpoint required.'; exit 1; }
[[ $(git rev-parse HEAD) == "$revision" ]] || { printf '%s\n' 'Checkout does not match the approved revision.'; exit 1; }
git diff --exit-code "$revision" -- backend
[[ -z $(git ls-files --others --exclude-standard backend) ]] || { printf '%s\n' 'Untracked backend source found.'; exit 1; }
jar=${3:-$source_root/backend/target/backend-0.0.1-SNAPSHOT.jar}
[[ -f $jar && ! -L $jar ]] || { printf '%s\n' 'Build and test the backend JAR first.'; exit 1; }
python3 - "$jar" <<'PY'
import sys
import zipfile
with zipfile.ZipFile(sys.argv[1]) as jar:
    manifest = jar.read('META-INF/MANIFEST.MF').decode()
    if 'Spring-Boot-Version: 4.1.1' not in manifest:
        raise SystemExit('Expected Spring Boot 4.1.1 executable JAR.')
PY
image="heshan-backend:$revision"
if docker image inspect "$image" >/dev/null 2>&1; then
  printf '%s\n' 'SHA tag already exists; refusing to overwrite it.'; exit 1
fi
[[ ! -e $output && ! -L $output ]] || { printf '%s\n' 'Output already exists; refusing to overwrite it.'; exit 1; }
mkdir -- "$output"
output=$(cd -- "$output" && pwd)
mkdir -p "$output/context" "$output/bundle/docs/scripts" "$output/bundle/deploy"
git archive "$revision" backend/Dockerfile backend/.dockerignore | tar -x -C "$output/context"
mkdir -p "$output/context/backend/target"
cp -- "$jar" "$output/context/backend/target/"
shasum -a 256 "$jar" > "$output/jar.sha256"
docker buildx build --platform linux/amd64 --load --build-arg "VCS_REF=$revision" \
  -t "$image" "$output/context/backend" 2>&1 | tee "$output/build.log"
[[ $(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image") == linux/amd64 ]]
[[ $(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image") == "$revision" ]]
docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}} {{index .Config.Labels "org.opencontainers.image.revision"}}' "$image" > "$output/image-identity.txt"
docker save --output "$output/bundle/backend-image.tar" "$image"
printf '%s\n' "$revision" > "$output/bundle/SOURCE_REVISION"
for file in run-vps-release-test.sh run-vps-postgresql-test.sh test-vps-postgresql.py pg-test-compose.yml; do
  cp -- "$root/docs/scripts/$file" "$output/bundle/docs/scripts/"
done
cp -- "$root/deploy/postgres-init.sh" "$output/bundle/deploy/"
cd "$output/bundle"
shasum -a 256 backend-image.tar SOURCE_REVISION docs/scripts/run-vps-release-test.sh \
  docs/scripts/run-vps-postgresql-test.sh docs/scripts/test-vps-postgresql.py \
  docs/scripts/pg-test-compose.yml deploy/postgres-init.sh > SHA256SUMS
tar -czf "$output/vps-release-test.tar.gz" .
shasum -a 256 "$output/vps-release-test.tar.gz" > "$output/bundle.sha256"
printf 'Prepared image: %s\nBundle: %s/vps-release-test.tar.gz\n' "$image" "$output"
cat "$output/image-identity.txt" "$output/bundle.sha256"
