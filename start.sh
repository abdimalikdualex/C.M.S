#!/usr/bin/env bash
# Run migrations before serving traffic (covers hosts where Procfile release is skipped).
set -o errexit

python manage.py migrate --no-input
python manage.py create_default_admin

exec gunicorn college_management_system.wsgi --log-file -
