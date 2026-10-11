#!/usr/bin/env bash
set -euo pipefail
umask 077
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ $# -ne 1 || $1 != /* || -e $1 || -L $1 ]]; then
  printf '%s\n' 'Supply a new absolute archive path; existing files are never overwritten.' >&2
  exit 1
fi
# Exclusively reserve the output; bundle contains no env files, keys or databases.
(set -o noclobber; : > "$1")
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$1" -C "$root" \
  docs/scripts/run-vps-postgresql-test.sh \
  docs/scripts/test-vps-postgresql.py \
  docs/scripts/pg-test-compose.yml \
  deploy/postgres-init.sh
printf 'Prepared script-only bundle: %s\n' "$1"
printf '%s\n' 'The approved prebuilt AMD64 backend image must be supplied separately.'
