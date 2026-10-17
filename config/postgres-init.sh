#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_password="$APP_DB_PASSWORD" --set=grafana_password="$GRAFANA_DB_PASSWORD" <<'SQL'
CREATE ROLE jls_app LOGIN PASSWORD :'app_password';
CREATE ROLE jls_grafana LOGIN PASSWORD :'grafana_password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA jls AUTHORIZATION jls_app;
GRANT USAGE ON SCHEMA jls TO jls_grafana;
ALTER DEFAULT PRIVILEGES FOR ROLE jls_app IN SCHEMA jls GRANT SELECT ON TABLES TO jls_grafana;
SQL
