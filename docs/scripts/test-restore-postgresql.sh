#!/usr/bin/env bash
set -Eeuo pipefail
set +x
[[ $# == 1 && -f $1 ]] || { printf 'Usage: bash test-restore-postgresql.sh /absolute/path/backup.dump\n' >&2; exit 1; }
endpoint=${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}' "$(docker context show)")}
case "$endpoint" in unix://*|npipe://*) ;; *) printf 'Restore tests require a local Docker socket.\n' >&2; exit 1;; esac
docker info >/dev/null
name="heshan-restore-test-$(date +%s)-$$"
created=false
cleanup() {
    if [[ $created == true ]]; then docker rm -f "$name" >/dev/null; fi
}
trap cleanup EXIT
export POSTGRES_PASSWORD
POSTGRES_PASSWORD=$(openssl rand -hex 32)
# Disposable tmpfs database; no production volume or published port is used.
docker run -d --name "$name" --network none --memory 384m --cpus 0.5 \
    --tmpfs /var/lib/postgresql/data:rw,size=512m \
    --env POSTGRES_PASSWORD --env POSTGRES_DB=restore_test postgres:16-bookworm >/dev/null
created=true
ready=false
for attempt in {1..60}; do
    if docker exec "$name" pg_isready -h 127.0.0.1 -U postgres -d restore_test >/dev/null 2>&1; then ready=true; break; fi
    sleep 1
done
[[ $ready == true ]] || { printf 'Temporary database did not become ready.\n' >&2; exit 1; }
docker exec -i "$name" pg_restore --exit-on-error --no-owner --no-acl -U postgres -d restore_test < "$1"
docker exec -i "$name" psql -v ON_ERROR_STOP=1 -U postgres -d restore_test <<'SQL'
SELECT 'users' AS table_name, count(*) FROM users
UNION ALL SELECT 'posts', count(*) FROM posts
UNION ALL SELECT 'comments', count(*) FROM comments
UNION ALL SELECT 'founder_identity', count(*) FROM founder_identity
UNION ALL SELECT 'role_change_audit', count(*) FROM role_change_audit;
SELECT version, success FROM flyway_schema_history ORDER BY installed_rank;
SQL
printf 'Isolated restore completed. Compare counts and critical records against the backup reference.\n'
