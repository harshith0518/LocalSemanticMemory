#!/bin/sh
set -eu

# PostgreSQL runs this only when initializing an empty data volume.
psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=db="$POSTGRES_DB" --set=app_user="$APP_USER" --set=app_password="$APP_PASSWORD" \
  --set=migration_user="$MIGRATION_USER" --set=migration_password="$MIGRATION_PASSWORD" <<'SQL'
CREATE ROLE jarvis_runtime NOLOGIN;
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password' IN ROLE jarvis_runtime;
CREATE ROLE :"migration_user" LOGIN PASSWORD :'migration_password';
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"app_user", :"migration_user";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE EXTENSION vector;
CREATE SCHEMA jarvis AUTHORIZATION :"migration_user";
GRANT USAGE ON SCHEMA jarvis TO jarvis_runtime;
SQL
