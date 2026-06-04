#!/usr/bin/env bash
# Run the full College Management System locally (app + SQLite in one go).
set -o errexit
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
# shellcheck source=/dev/null
source venv/bin/activate

pip install -r requirements.txt
export USE_SQLITE=1
python manage.py migrate --no-input
python manage.py create_default_admin
echo "Starting server at http://127.0.0.1:8000/ (database: db.sqlite3)"
exec python manage.py runserver 0.0.0.0:8000
