#!/usr/bin/env bash
# Read only: fixed Staging containers, synthetic users, no config/secret output.
set -euo pipefail
if [[ $EUID -ne 0 || $# -ne 2 ]]; then
  printf 'Run with interactive sudo and API/UI synthetic usernames.\n' >&2
  exit 1
fi
for name in "$@"; do
  if [[ ! $name =~ ^stage-(api|ui)-[a-z0-9]{6,20}$ ]]; then
    printf 'Only synthetic acceptance usernames are allowed.\n' >&2
    exit 1
  fi
done

for container in heshan-staging-db-1 heshan-staging-backend-1 heshan-staging-web-1; do
  test "$(docker inspect "$container" --format '{{index .Config.Labels "com.docker.compose.project"}}')" = heshan-staging
  docker inspect "$container" --format '{{.Name}} Health={{.State.Health.Status}} OOM={{.State.OOMKilled}} Restarts={{.RestartCount}} Ports={{json .NetworkSettings.Ports}}'
  printf 'Recent log summary: %s\n' "$container"
  docker logs --since 30m "$container" 2>&1 | python3 -c '
import re, sys
counts = dict(errors=0, warnings=0, oom=0)
for line in sys.stdin:
    counts["errors"] += bool(re.search(r"\b(ERROR|FATAL|PANIC|Exception)\b", line))
    counts["warnings"] += bool(re.search(r"\bWARN(?:ING)?\b", line))
    counts["oom"] += bool(re.search(r"OutOfMemory|OOMKilled", line))
print(counts)
'
done
docker stats --no-stream heshan-staging-db-1 heshan-staging-backend-1 heshan-staging-web-1
free -m
df -h /

docker exec -i heshan-staging-db-1 sh -c '
  test "$POSTGRES_DB" = heshan_staging
  exec psql -X -U postgres -d heshan_staging -v ON_ERROR_STOP=1 -v api_user="$1" -v ui_user="$2"
' sh "$1" "$2" <<'SQL'
BEGIN READ ONLY;
SELECT current_database() AS database_name;
SELECT id, username, role FROM users
WHERE username IN (:'api_user', :'ui_user') ORDER BY id;
SELECT 'synthetic_users_default_USER' AS check_name,
       CASE WHEN count(*) = 2 AND bool_and(role = 'USER') THEN 'PASS' ELSE 'FAIL' END AS result
FROM users WHERE username IN (:'api_user', :'ui_user');
SELECT u.username, p.id AS post_id, p.type, p.ip_location_status
FROM posts p JOIN users u ON p.author_id = u.id
WHERE u.username IN (:'api_user', :'ui_user') ORDER BY p.id;
SELECT 'synthetic_posts_saved' AS check_name,
       CASE WHEN count(*) = 4 THEN 'PASS' ELSE 'FAIL' END AS result
FROM posts p JOIN users u ON p.author_id = u.id
WHERE u.username IN (:'api_user', :'ui_user');
SELECT u.username, c.id AS comment_id, c.post_id, c.ip_location_status
FROM comments c JOIN users u ON c.user_id = u.id
WHERE u.username IN (:'api_user', :'ui_user') ORDER BY c.id;
SELECT 'synthetic_comments_saved' AS check_name,
       CASE WHEN count(*) = 4 THEN 'PASS' ELSE 'FAIL' END AS result
FROM comments c JOIN users u ON c.user_id = u.id
WHERE u.username IN (:'api_user', :'ui_user');
SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank;
COMMIT;
SQL
