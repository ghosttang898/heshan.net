#!/usr/bin/env bash
set -Eeuo pipefail
set +x
umask 077
[[ $# == 0 ]] || { printf 'No arguments accepted.\n' >&2; exit 1; }
offsite=${BACKUP_OFFSITE:-0}
[[ $offsite == 0 || $offsite == 1 ]] || { printf 'BACKUP_OFFSITE must be 0 or 1.\n' >&2; exit 1; }
: "${ENV_FILE:?Set the absolute server-local Compose env file path}"
: "${COMPOSE_FILE:?Set the absolute deploy/compose.yml path}"
: "${BACKUP_DIR:?Set the absolute backup directory, matching the env file}"
[[ $ENV_FILE == /* && $COMPOSE_FILE == /* && $BACKUP_DIR == /* ]] || exit 1
[[ -f $ENV_FILE && -f $COMPOSE_FILE ]] || exit 1
[[ $(stat -c '%a' "$ENV_FILE") == 600 ]] || { printf 'Compose env file must have mode 0600.\n' >&2; exit 1; }
export BACKUP_DIR
install -d -m 0700 "$BACKUP_DIR"
exec 9>"$BACKUP_DIR/.backup.lock"
flock -n 9 || { printf 'Backup already running.\n' >&2; exit 1; }
compose=(docker --host unix:///var/run/docker.sock compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
"${compose[@]}" config --quiet
name="heshan-$(date -u +%Y%m%dT%H%M%SZ).dump"
partial=$(mktemp "$BACKUP_DIR/.partial.XXXXXXXX")
"${compose[@]}" exec -T db sh -ec 'PGPASSWORD="$APP_DB_PASSWORD"; export PGPASSWORD; exec pg_dump -h 127.0.0.1 -Fc -Z 3 --no-owner --no-acl -U "$APP_DB_USER" -d "$POSTGRES_DB"' > "$partial"
[[ -s $partial ]] || { printf 'Empty backup rejected; partial file retained.\n' >&2; exit 1; }
[[ ! -e $BACKUP_DIR/$name ]] || exit 1
mv -- "$partial" "$BACKUP_DIR/$name"
(cd "$BACKUP_DIR"; sha256sum "$name" > "$name.sha256")
(cd "$BACKUP_DIR"; sha256sum -c "$name.sha256")
"${compose[@]}" exec -T db pg_restore --list < "$BACKUP_DIR/$name" > "$BACKUP_DIR/$name.toc"
[[ -s $BACKUP_DIR/$name.toc ]] || { printf 'Empty archive listing rejected.\n' >&2; exit 1; }
# MVP default is local-only; retained legacy offsite support needs explicit opt-in.
if [[ $offsite == 1 ]]; then
  "${compose[@]}" --profile backup run --rm --no-deps offsite
  printf 'Database dump and offsite transfer completed; no backups pruned.\n'
else
  printf 'PASS: local dump, SHA256 and archive listing; offsite NOT RUN; no backups pruned.\n'
fi
# Upload exit status alone is not proof that each old remote object is intact.
# Keep everything until an approved per-object download/SHA256 retention gate.
