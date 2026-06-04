#!/usr/bin/env bash
# Render (and other PaaS) build script.
# Installs dependencies and collects static files only.
# Database migrations and admin seeding run in the Procfile "release" phase
# (after deploy, when DATABASE_URL is reachable on Render's private network).

set -o errexit

export USE_SQLITE=1
export SINGLE_STACK=1
unset DATABASE_URL
unset DATABASE_EXTERNAL_URL

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
