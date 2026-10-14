#!/usr/bin/env bash
# Legacy one-argument restore is intentionally rejected by the guarded runner.
set -Eeuo pipefail
set +x
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/isolated-postgresql-restore.py" "$@"
