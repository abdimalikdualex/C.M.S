#!/usr/bin/env bash
# Render (and other PaaS) build script.
# Installs dependencies, collects static files, applies migrations,
# and makes sure a default HOD login exists so a fresh deploy is usable.

set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py create_default_admin
