#!/usr/bin/env bash
# Run migrations before serving traffic (covers hosts where Procfile release is skipped).
set -o errexit

# Persistent disk is mounted only at runtime, not during the build step.
if [ -n "${RENDER_DISK_PATH:-}" ]; then
  mkdir -p "${RENDER_DISK_PATH}"
  if [ -n "${MEDIA_ROOT:-}" ]; then
    mkdir -p "${MEDIA_ROOT}"
  else
    mkdir -p "${RENDER_DISK_PATH}/media"
  fi
fi

python manage.py migrate --no-input
python manage.py check_database

# Creates the default HOD only if missing — never deletes data or resets passwords.
python manage.py create_default_admin || echo "create_default_admin: skipped or already exists"

exec gunicorn college_management_system.wsgi --log-file -
