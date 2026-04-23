release: python manage.py migrate --no-input && python manage.py create_default_admin
web: gunicorn college_management_system.wsgi --log-file -
