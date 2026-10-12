#!/usr/bin/env bash
# Owner-approved backup only. Never stop, rebuild, initialize or restore services.
set -Eeuo pipefail
set +x
umask 077
[[ $EUID == 0 && $# == 1 && $1 == --execute-backup ]] || {
  printf 'Use interactive sudo with --execute-backup after owner approval.\n' >&2; exit 1;
}
[[ $(uname -s) == Linux ]] || exit 1
unset DOCKER_CONTEXT
export DOCKER_HOST=unix:///var/run/docker.sock
report=$(mktemp -d /var/tmp/heshan-staging-preupdate-XXXXXXXX)
chmod 0700 "$report"
backup=
finish() {
  local code=$?
  trap - EXIT
  python3 - "$report" "$code" "$backup" <<'PY'
import json, pathlib, sys
directory = pathlib.Path(sys.argv[1])
(directory / 'result.json').write_text(json.dumps({
    'status': 'PASS' if sys.argv[2] == '0' else 'FAIL',
    'exit_code': int(sys.argv[2]), 'backup': sys.argv[3],
    'containers_modified': False, 'database_restored': False,
    'report_directory': str(directory)}, indent=2) + '\n')
PY
  printf 'Backup phase exit: %s\nReport: %s\nNo container or existing data was changed.\n' "$code" "$report"
  exit "$code"
}
trap finish EXIT
exec > >(tee "$report/execution.log") 2>&1
for container in heshan-staging-db-1 heshan-staging-backend-1 heshan-staging-web-1; do
  [[ $(docker inspect "$container" --format '{{index .Config.Labels "com.docker.compose.project"}}') == heshan-staging ]]
  [[ $(docker inspect "$container" --format '{{.State.Health.Status}}') == healthy ]]
  [[ $(docker inspect "$container" --format '{{.State.OOMKilled}}') == false ]]
  docker inspect "$container" --format '{{.Name}} ID={{.Id}} Image={{.Config.Image}} Health={{.State.Health.Status}} Restarts={{.RestartCount}} Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}} Ports={{json .NetworkSettings.Ports}}'
done
[[ $(docker port heshan-staging-web-1 8443/tcp) == 127.0.0.1:18443 ]]
[[ -f /etc/heshan-staging/web-ingress.override.yml && ! -L /etc/heshan-staging/web-ingress.override.yml ]]
[[ $(stat -c '%a %u' /etc/heshan-staging/web-ingress.override.yml) == '600 0' ]]
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
  --cacert /etc/heshan-staging/tls/rootCA.pem -o /dev/null https://localhost:18443/api/health
docker exec heshan-staging-db-1 sh -ec 'test "$POSTGRES_DB" = heshan_staging'
awk '/MemAvailable:/ {if ($2 < 524288) exit 1}' /proc/meminfo
df -Pk /var/backups | awk 'NR == 2 {if ($4 < 4194304) exit 1}'

baseline() {
  docker exec -i heshan-staging-db-1 sh -ec \
    'exec psql -X -U postgres -d heshan_staging -v ON_ERROR_STOP=1 -At' <<'SQL'
BEGIN READ ONLY;
SELECT json_build_object(
 'users',(SELECT count(*) FROM users),
 'posts',(SELECT count(*) FROM posts),
 'comments',(SELECT count(*) FROM comments),
 'founders',(SELECT count(*) FROM founder_identity),
 'audits',(SELECT count(*) FROM role_change_audit),
 'users_fingerprint',(SELECT md5(coalesce(string_agg(id||':'||username||':'||role, '|' ORDER BY id),'')) FROM users),
 'posts_fingerprint',(SELECT md5(coalesce(string_agg(id||':'||title||':'||content||':'||status, '|' ORDER BY id),'')) FROM posts),
 'comments_fingerprint',(SELECT md5(coalesce(string_agg(id||':'||post_id||':'||content||':'||status, '|' ORDER BY id),'')) FROM comments),
 'flyway',(SELECT json_agg(json_build_object('version',version,'success',success) ORDER BY installed_rank) FROM flyway_schema_history)
);
COMMIT;
SQL
}
baseline > "$report/baseline-before.txt"
directory=/var/backups/heshan-staging
[[ ! -L "$directory" ]]
if [[ -e "$directory" ]]; then
  [[ -d "$directory" && $(stat -c '%a %u' "$directory") == '700 0' ]]
else
  install -d -m 0700 -o root -g root "$directory"
fi
exec 9>"$directory/.preupdate-backup.lock"
flock -n 9 || { printf 'Another preupdate backup holds the lock.\n' >&2; exit 1; }
partial=$(mktemp "$directory/preupdate-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXXXX.dump.partial")
docker exec heshan-staging-db-1 sh -ec \
  'PGPASSWORD="$APP_DB_PASSWORD"; export PGPASSWORD; exec pg_dump -h 127.0.0.1 -U "$APP_DB_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' > "$partial"
[[ -s "$partial" ]]
backup=${partial%.partial}
[[ ! -e "$backup" ]]
mv -n -- "$partial" "$backup"
[[ ! -e "$partial" ]]
sha256sum "$backup" > "$backup.sha256"
docker exec -i heshan-staging-db-1 pg_restore --list < "$backup" > "$report/backup-toc.txt"
baseline > "$report/baseline-after.txt"
cmp "$report/baseline-before.txt" "$report/baseline-after.txt" || {
  printf 'Concurrent writes detected. Backup retained; repeat baseline phase while idle.\n' >&2; exit 1;
}
free -m
df -h /
docker stats --no-stream heshan-staging-db-1 heshan-staging-backend-1 heshan-staging-web-1
printf 'PASS: nonempty dump, checksum and archive listing; unchanged data baseline.\nBackup: %s\n' "$backup"
