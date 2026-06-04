#!/usr/bin/env bash
# Run migrations before serving traffic (covers hosts where Procfile release is skipped).
set -o errexit

# Single-stack: SQLite only — ignore any legacy linked Postgres DATABASE_URL on Render.
export USE_SQLITE=1
export SINGLE_STACK=1
unset DATABASE_URL
unset DATABASE_EXTERNAL_URL

# Persistent disk is mounted only at runtime, not during the build step.
if [ -n "${RENDER_DISK_PATH:-}" ]; then
  mkdir -p "${RENDER_DISK_PATH}"
  if [ -n "${MEDIA_ROOT:-}" ]; then
    mkdir -p "${MEDIA_ROOT}"
  else
    mkdir -p "${RENDER_DISK_PATH}/media"
  fi
fi

# First boot: copy bundled db.sqlite3 onto the persistent disk if present in the repo.
TARGET_DB="${SQLITE_PATH:-}"
if [ -z "$TARGET_DB" ] && [ -n "${RENDER_DISK_PATH:-}" ]; then
  TARGET_DB="${RENDER_DISK_PATH}/db.sqlite3"
fi
if [ -n "$TARGET_DB" ] && [ ! -f "$TARGET_DB" ] && [ -f "db.sqlite3" ]; then
  cp "db.sqlite3" "$TARGET_DB"
  echo "Copied db.sqlite3 to $TARGET_DB"
fi

python manage.py migrate --no-input
python manage.py check_database

# Creates the default HOD only if missing — never deletes data or resets passwords.
python manage.py create_default_admin || echo "create_default_admin: skipped or already exists"

exec gunicorn college_management_system.wsgi --log-file -
