#!/usr/bin/env bash
# Run migrations before serving traffic (covers hosts where Procfile release is skipped).
set -o errexit

python manage.py migrate --no-input

# Bootstrap / sync HOD login from Render env (DEFAULT_ADMIN_EMAIL + DEFAULT_ADMIN_PASSWORD).
if [ -n "${SYNC_ADMIN_PASSWORD:-}" ]; then
  python manage.py create_default_admin --reset-password
else
  python manage.py create_default_admin || echo "create_default_admin: skipped or already exists"
fi

exec gunicorn college_management_system.wsgi --log-file -
