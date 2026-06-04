#!/usr/bin/env bash
# Run migrations before serving traffic (covers hosts where Procfile release is skipped).
set -o errexit

python manage.py migrate --no-input

# Creates the default HOD only if missing — never deletes data or resets passwords.
python manage.py create_default_admin || echo "create_default_admin: skipped or already exists"

exec gunicorn college_management_system.wsgi --log-file -
