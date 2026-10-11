#!/usr/bin/env bash
set -euo pipefail
umask 077
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
jar="$root/backend/target/backend-0.0.1-SNAPSHOT.jar"
[[ -s "$jar" ]] || { printf '%s\n' 'Run the Java 17 Maven tests/package successfully first.' >&2; exit 1; }
stage=$(mktemp -d "${TMPDIR:-/tmp}/heshan-pg-ready-XXXXXXXX")
mkdir -p "$stage/target" "$stage/docs/scripts" "$stage/deploy"
cp "$root/backend/Dockerfile" "$root/backend/.dockerignore" "$stage/"
cp "$jar" "$stage/target/"
for file in prepare-vps-postgresql-images.sh run-vps-postgresql-test.sh test-vps-postgresql.py pg-test-compose.yml; do
  cp "$root/docs/scripts/$file" "$stage/docs/scripts/"
done
cp "$root/deploy/postgres-init.sh" "$stage/deploy/"
cd "$stage"
shasum -a 256 Dockerfile .dockerignore target/backend-0.0.1-SNAPSHOT.jar \
  docs/scripts/prepare-vps-postgresql-images.sh docs/scripts/run-vps-postgresql-test.sh \
  docs/scripts/test-vps-postgresql.py docs/scripts/pg-test-compose.yml deploy/postgres-init.sh > SHA256SUMS
archive=$(mktemp "${TMPDIR:-/tmp}/heshan-pg-upload-XXXXXXXX")
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$archive" Dockerfile .dockerignore target docs deploy SHA256SUMS
printf 'Bundle: %s\n' "$archive"
shasum -a 256 "$archive"
printf '%s\n' 'Contains only the prebuilt JAR and reviewed test/build files. No production env, keys or database.'
