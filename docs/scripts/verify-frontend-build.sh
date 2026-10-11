#!/usr/bin/env bash
set -euo pipefail
umask 077
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
[[ -z ${DOCKER_CONTEXT:-} ]] || { printf '%s\n' 'Unset DOCKER_CONTEXT and use a local Docker socket.' >&2; exit 1; }
endpoint=${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}
case "$endpoint" in unix://*|npipe://*) ;; *) printf '%s\n' 'Remote Docker hosts are not permitted.' >&2; exit 1 ;; esac
docker info >/dev/null
workspace=$(mktemp -d "${TMPDIR:-/tmp}/heshan-frontend-build-XXXXXXXX")
cp -R "$root/frontend/src" "$root/frontend/public" "$root/frontend/index.html" \
  "$root/frontend/package.json" "$root/frontend/package-lock.json" "$root/frontend/vite.config.js" "$workspace/"
# Fresh dependencies/cache avoid iCloud placeholders without changing the existing node_modules.
image=${NODE_BUILD_IMAGE:-node:24-bookworm-slim}
printf 'Isolated frontend workspace: %s\n' "$workspace"
docker run --rm --memory 1g --cpus 1 \
  --mount "type=bind,source=$workspace,target=/workspace" --workdir /workspace \
  --env "VITE_API_BASE_URL=${VITE_API_BASE_URL:-https://api.heshan.net/api}" \
  "$image" sh -ec 'npm ci --no-audit --no-fund; npm test; npm run build'
docker image inspect --format 'Build image: {{.Id}}' "$image"
printf 'Verified build retained at: %s/dist\n' "$workspace"
