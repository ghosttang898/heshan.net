#!/usr/bin/env bash
set -Eeuo pipefail
set +x
umask 077
[[ $# == 0 ]] || { printf 'No arguments accepted.\n' >&2; exit 1; }
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
# Failed offsite upload fails the job and leaves local backups intact.
"${compose[@]}" --profile backup run --rm --no-deps offsite
find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'heshan-*.dump' -o -name 'heshan-*.dump.sha256' \) -mmin +10080 -delete
printf 'Database dump and offsite transfer completed.\n'
