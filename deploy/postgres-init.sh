#!/usr/bin/env bash
set -Eeuo pipefail
set +x
: "${APP_DB_USER:?required}"
: "${APP_DB_PASSWORD:?required}"
[[ $APP_DB_USER != postgres ]] || { printf 'Application role cannot be postgres.\n' >&2; exit 1; }
# psql quoting and getenv avoid putting credentials in command arguments.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_user APP_DB_USER
\getenv app_password APP_DB_PASSWORD
\getenv app_database POSTGRES_DB
CREATE ROLE :"app_user" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
ALTER DATABASE :"app_database" OWNER TO :"app_user";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
SQL
