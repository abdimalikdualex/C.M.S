#!/usr/bin/env bash
# Render (and other PaaS) build script.
# Installs dependencies and collects static files only.
# Database migrations and admin seeding run in the Procfile "release" phase
# (after deploy, when DATABASE_URL is reachable on Render's private network).

set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
