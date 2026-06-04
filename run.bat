@echo off
REM Run the full College Management System locally (app + SQLite in one go).
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat
pip install -r requirements.txt -q
python manage.py migrate --no-input
python manage.py create_default_admin
echo.
echo Starting server at http://127.0.0.1:8000/
echo Database file: db.sqlite3
python manage.py runserver
